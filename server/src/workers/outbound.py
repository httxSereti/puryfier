"""Outbound queue drain for a live Puryfi connection."""

import asyncio

import structlog

from domain.ports import LockSessionRepository, MessageQueue, OutboundConnection
from domain.use_cases.link_puryfi import link_puryfi
from realtime.protocol import intents

log = structlog.get_logger(__name__)


async def drain_queued_messages(
    *,
    connection: OutboundConnection,
    queue: MessageQueue,
    sessions: LockSessionRepository,
    link_token: str,
    intents_timeout: float,
) -> None:
    """Deliver durable commands in order, once intents were granted.

    Messages are deleted only after a successful send, so a crash mid-drain
    cannot lose them. Ordering is semantic for the lock/unlock protocol.
    """
    try:
        await asyncio.wait_for(
            connection.intents_granted_event.wait(),
            timeout=intents_timeout,
        )
    except TimeoutError:
        log.warning("connection.queue_intents_timeout")
        return

    session = await link_puryfi(link_token, sessions=sessions)
    if session is None:
        return

    # The Puryfi handshake completed: tell the extension UI that the plugin is
    # now linked, without waiting for a page refresh.
    await connection.on_linked(session)

    queued_messages = await queue.fetch(link_token)

    for command in queued_messages:
        log.debug(
            "queue.sending",
            session_id=session.session_id,
            message_type=command.msg_type,
        )
        res = await connection.send_message(command.msg_type, command.payload)

        if isinstance(res, dict) and res.get("type") == "error":
            error_name = res.get("name")
            error_msg = res.get("message")
            log.warning(
                "queue.send_failed",
                session_id=session.session_id,
                message_type=command.msg_type,
                error_name=error_name,
                error=error_msg,
            )

            if error_name == "missingPluginIntents":
                # Keep the message queued for the next drain and re-request intents.
                await connection.send_message("requestPluginIntents", {"intents": intents})
                return

            # Other errors: stop draining and keep this and the remaining
            # messages queued rather than dropping them out of order.
            return

        # Delivered: only now is it safe to remove it from the queue.
        await queue.delete(command)
