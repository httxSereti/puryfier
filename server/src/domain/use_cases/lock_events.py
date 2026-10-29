"""Chaster lock lifecycle webhook handlers."""

import secrets

import structlog

from domain.events import extract_session_id
from domain.ports import LockSessionRepository, MessageQueue, PuryfiRegistry

log = structlog.get_logger(__name__)


async def handle_lock_frozen(
    payload: dict,
    *,
    sessions: LockSessionRepository,
    queue: MessageQueue,
    puryfi: PuryfiRegistry,
) -> dict:
    """Handle the 'lock_frozen' event action from Chaster."""
    session_id = extract_session_id(payload)

    if not session_id:
        log.warning("webhook.lock_frozen.no_session")
        return {"status": "ok", "action": "lock_frozen_ignored_no_session"}

    session = await sessions.get_by_session_id(session_id)

    if session is None or not session.config:
        log.warning("webhook.lock_frozen.no_config", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_no_config"}

    if not session.link_token:
        log.warning("webhook.lock_frozen.no_link_token", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_no_link_token"}

    if not session.config.lock_on_freeze:
        log.debug("webhook.lock_frozen.disabled", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_config_false"}

    connection = puryfi.get(session.link_token)

    generated_password = secrets.token_urlsafe(16)
    await sessions.update(session_id, lock_password=generated_password)
    session.lock_password = generated_password

    if connection:
        log.info(
            "webhook.lock_frozen.connection_found",
            session_id=session_id,
        )
        # Send both state changes as one ordered mailbox batch: no other
        # command can interleave between them.
        await connection.send_messages(
            [
                ("setState", {"path": "enabled", "value": True}),
                (
                    "setState",
                    {
                        "path": "lockConfiguration",
                        "value": {"password": {"secret": generated_password}},
                    },
                ),
            ]
        )
        return {"status": "ok", "action": "lock_frozen_processed"}

    log.info("webhook.lock_frozen.queued", session_id=session_id)
    await queue.enqueue(
        session.link_token, "setState", {"path": "enabled", "value": True}
    )
    await queue.enqueue(
        session.link_token,
        "setState",
        {
            "path": "lockConfiguration",
            "value": {"password": {"secret": generated_password}},
        },
    )
    return {"status": "ok", "action": "lock_frozen_queued_no_connection"}


async def handle_lock_unfrozen(
    payload: dict,
    *,
    sessions: LockSessionRepository,
    queue: MessageQueue,
    puryfi: PuryfiRegistry,
) -> dict:
    """Handle the 'lock_unfrozen' event action from Chaster."""
    session_id = extract_session_id(payload)

    if not session_id:
        log.warning("webhook.lock_unfrozen.no_session")
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_session"}

    session = await sessions.get_by_session_id(session_id)

    if session is None or not session.config:
        log.warning("webhook.lock_unfrozen.no_config", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_config"}

    if not session.link_token:
        log.warning("webhook.lock_unfrozen.no_link_token", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_link_token"}

    if not session.config.unlock_on_unfreeze:
        log.debug("webhook.lock_unfrozen.disabled", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_config_false"}

    connection = puryfi.get(session.link_token)
    retrieved_password = session.lock_password

    if not retrieved_password:
        # Never send {"secret": None} to the plugin.
        log.warning("webhook.lock_unfrozen.no_password", session_id=session_id)
        return {"status": "error", "error": "no_lock_password"}

    if connection:
        log.info(
            "webhook.lock_unfrozen.connection_found",
            session_id=session_id,
        )
        unlock_response = await connection.send_message(
            "enterLockPassword", {"secret": retrieved_password}
        )

        if isinstance(unlock_response, dict) and unlock_response.get("type") == "ok":
            await connection.send_message(
                "setState", {"path": "enabled", "value": False}
            )
        else:
            error = (
                unlock_response.get("error", "unknown_error")
                if isinstance(unlock_response, dict)
                else "unknown_error"
            )
            log.warning(
                "webhook.lock_unfrozen.failed",
                session_id=session_id,
                error=error,
            )
            return {"status": "error", "error": error}

        log.info("webhook.lock_unfrozen.processed", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_processed"}

    log.info("webhook.lock_unfrozen.queued", session_id=session_id)
    await queue.enqueue(
        session.link_token, "enterLockPassword", {"secret": retrieved_password}
    )
    await queue.enqueue(
        session.link_token, "setState", {"path": "enabled", "value": False}
    )
    return {"status": "ok", "action": "lock_unfrozen_queued_no_connection"}


async def handle_extension_updated(payload: dict) -> dict:
    """Handle the 'extension_updated' event action from Chaster."""
    log.info("webhook.extension_updated")
    # TODO: Implement extension_updated logic
    return {"status": "ok", "action": "extension_updated_processed"}
