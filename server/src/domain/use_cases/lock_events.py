"""Chaster lock lifecycle webhook handlers."""

import secrets

import structlog

from domain.events import extract_session_id
from domain.ports import (
    LockSessionRepository,
    MessageQueue,
    PuryfiConnection,
    PuryfiRegistry,
)
from domain.redaction import token_fingerprint

log = structlog.get_logger(__name__)

LockCommand = tuple[str, dict]


async def _queue_and_flush(
    *,
    queue: MessageQueue,
    puryfi: PuryfiRegistry,
    link_token: str,
    commands: list[LockCommand],
    log_event: str,
) -> tuple[PuryfiConnection | None, bool]:
    """Persist lock commands, then try to deliver them to a ready plugin.

    Commands always go through the durable queue: if PuryFi has not completed
    its handshake or has not granted the required intents yet, they stay queued
    and the bootstrap/``intentsGrant`` drain delivers them later. This makes a
    lock webhook lossless even when it races the plugin connection setup.

    Returns the live connection (if any) and whether the queue was fully
    drained. ``(None, False)`` means there was no connection at all.
    """
    connection = puryfi.get(link_token)

    for msg_type, payload in commands:
        await queue.enqueue(link_token, msg_type, payload)

    if connection is None:
        return None, False

    # Enforce readiness at the use-case boundary too: the durable queue is the
    # only safe place for commands until PuryFi acknowledged `ready` and
    # granted the required intents. The bootstrap or `intentsGrant` drain will
    # deliver them later.
    if not connection.ready or not connection.intents_granted:
        return connection, False

    try:
        return connection, await connection.flush_queue()
    except Exception:
        log.exception(
            f"{log_event}.flush_failed",
            link_token=token_fingerprint(link_token),
        )
        return connection, False


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

    generated_password = secrets.token_urlsafe(16)
    await sessions.update(session_id, lock_password=generated_password)
    session.lock_password = generated_password

    connection, delivered = await _queue_and_flush(
        queue=queue,
        puryfi=puryfi,
        link_token=session.link_token,
        commands=[
            (
                "setState",
                {
                    "path": "lockConfiguration",
                    # WriteOnlyValue<"lockConfiguration"> has three required
                    # fields. Send them explicitly: PuryFi replaces the whole
                    # value, and omitting timer/timerPlus relies on implicit
                    # null defaults instead of the SDK contract.
                    "value": {
                        "password": {"secret": generated_password},
                        "timer": None,
                        "timerPlus": None,
                    },
                },
            ),
            # Configure the lock before enabling PuryFi: the durable queue
            # stops at the first failed command, so a rejected
            # `lockConfiguration` can never be followed by `enabled=true`.
            # Retrying the sequence is safe because it converges to the same
            # state.
            ("setState", {"path": "enabled", "value": True}),
        ],
        log_event="webhook.lock_frozen",
    )

    if connection is None:
        log.info("webhook.lock_frozen.queued", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_queued_no_connection"}

    if not delivered:
        log.info(
            "webhook.lock_frozen.queued_not_ready",
            session_id=session_id,
            ready=getattr(connection, "ready", False),
            intents_granted=getattr(connection, "intents_granted", False),
        )
        return {"status": "ok", "action": "lock_frozen_queued_not_ready"}

    log.info("webhook.lock_frozen.processed", session_id=session_id)
    return {"status": "ok", "action": "lock_frozen_processed"}


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

    retrieved_password = session.lock_password

    if not retrieved_password:
        # Never send {"secret": None} to the plugin.
        log.warning("webhook.lock_unfrozen.no_password", session_id=session_id)
        return {"status": "error", "error": "no_lock_password"}

    connection, delivered = await _queue_and_flush(
        queue=queue,
        puryfi=puryfi,
        link_token=session.link_token,
        commands=[
            ("enterLockPassword", {"secret": retrieved_password}),
            ("setState", {"path": "enabled", "value": False}),
        ],
        log_event="webhook.lock_unfrozen",
    )

    if connection is None:
        log.info("webhook.lock_unfrozen.queued", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_queued_no_connection"}

    if not delivered:
        log.info(
            "webhook.lock_unfrozen.queued_not_ready",
            session_id=session_id,
            ready=getattr(connection, "ready", False),
            intents_granted=getattr(connection, "intents_granted", False),
        )
        return {"status": "ok", "action": "lock_unfrozen_queued_not_ready"}

    log.info("webhook.lock_unfrozen.processed", session_id=session_id)
    return {"status": "ok", "action": "lock_unfrozen_processed"}


async def handle_extension_updated(payload: dict) -> dict:
    """Handle the 'extension_updated' event action from Chaster."""
    log.info("webhook.extension_updated")
    # TODO: Implement extension_updated logic
    return {"status": "ok", "action": "extension_updated_processed"}
