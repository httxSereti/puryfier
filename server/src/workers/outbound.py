"""Outbound queue drain for a live Puryfi connection."""

import asyncio

import structlog

from domain.ports import LockSessionRepository, MessageQueue, OutboundConnection
from domain.use_cases.link_puryfi import link_puryfi
from realtime.protocol import intents

log = structlog.get_logger(__name__)

MISSING_INTENTS_ERRORS = frozenset({"missingPluginIntents", "missingIntents"})


def _error_name(response: dict) -> str | None:
    """Read a PuryFi error identifier from either protocol variant.

    The PuryFi 0.8.7.1 runtime puts the identifier in ``error`` while the SDK
    types and docs use ``name``; accept both so a missing intents grant is
    always recovered instead of silently keeping the command queued.
    """
    name = response.get("error") or response.get("name")
    return name if isinstance(name, str) else None


async def drain_queued_messages(
    *,
    connection: OutboundConnection,
    queue: MessageQueue,
    sessions: LockSessionRepository,
    link_token: str,
    intents_timeout: float,
    wait_for_intents: bool = True,
) -> bool:
    """Deliver durable commands in order, once intents were granted.

    Messages are deleted only after a successful send, so a crash mid-drain
    cannot lose them. Ordering is semantic for the lock/unlock protocol.

    Returns True only when the queue was fully drained. On any failure the
    undelivered messages stay queued for the next drain (reconnect,
    ``intentsGrant``, or a later webhook flush).
    """
    if wait_for_intents:
        try:
            await asyncio.wait_for(
                connection.intents_granted_event.wait(),
                timeout=intents_timeout,
            )
        except TimeoutError:
            log.warning("connection.queue_intents_timeout")
            return False
    elif not connection.intents_granted:
        return False

    session = await link_puryfi(link_token, sessions=sessions)
    if session is None:
        return False

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
        try:
            res = await connection.send_message(command.msg_type, command.payload)
        except (ConnectionError, TimeoutError):
            log.warning(
                "queue.send_exception",
                session_id=session.session_id,
                message_type=command.msg_type,
            )
            return False

        if isinstance(res, dict) and res.get("type") == "error":
            error_name = _error_name(res)
            error_msg = res.get("message")
            log.warning(
                "queue.send_failed",
                session_id=session.session_id,
                message_type=command.msg_type,
                error_name=error_name,
                error=error_msg,
            )

            if error_name in MISSING_INTENTS_ERRORS:
                # Keep the message queued for the next drain and re-request
                # intents. The `intentsGrant` handler triggers that drain.
                try:
                    await connection.send_message(
                        "requestPluginIntents", {"intents": intents}
                    )
                except (ConnectionError, TimeoutError):
                    pass
            return False

        # Delivered: only now is it safe to remove it from the queue.
        await queue.delete(command)

    return True
