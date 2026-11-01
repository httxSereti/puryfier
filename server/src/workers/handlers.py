"""Webhook handlers bound to the active application container.

Keeping the dependency wiring here means the domain use cases stay pure while
the worker (and the legacy ``routes.webhooks.actions`` import path) sees simple
``handler(payload)`` callables. The container is resolved at call time so a
fresh app instance (tests, embedded usage) never reuses stale adapters.
"""

from container import get_active_container
from domain.automation_models import (
    EVENT_CHASTER_LOCK_FROZEN,
    EVENT_CHASTER_LOCK_UNFROZEN,
    EVENT_CHASTER_SESSION_JOINED,
    EVENT_CHASTER_SESSION_LEFT,
)
from domain.entities import ChasterExtensionConfigSchema
from domain.events import build_event_key, extract_session_id
from domain.use_cases.lock_events import (
    handle_extension_updated as _handle_extension_updated,
)
from domain.use_cases.lock_events import handle_lock_frozen as _handle_lock_frozen
from domain.use_cases.lock_events import handle_lock_unfrozen as _handle_lock_unfrozen
from domain.use_cases.session_lifecycle import (
    handle_extension_session_deleted as _handle_extension_session_deleted,
)


async def _handle_with_automations(payload: dict, event_type: str, frozen: bool) -> dict | None:
    """Run the automation engine when the session opted into automation mode."""
    container = get_active_container()
    session_id = extract_session_id(payload)
    if not session_id:
        return None

    session = await container.session_repository.get_by_session_id(session_id)
    if session is None or not session.automation_mode:
        return None

    try:
        event_id = build_event_key(payload) or payload.get("requestId")
    except (TypeError, ValueError):
        event_id = payload.get("requestId")
    if not event_id:
        event_id = f"{event_type}:{session_id}"

    executions = await container.automation_engine.evaluate_event(
        session,
        event_type=event_type,
        payload=payload,
        context={"chaster_frozen": frozen},
        event_id=str(event_id),
    )
    return {
        "status": "ok",
        "action": "automation_processed",
        "executions": len(executions),
    }


async def handle_lock_frozen(payload: dict) -> dict:
    automated = await _handle_with_automations(
        payload, EVENT_CHASTER_LOCK_FROZEN, frozen=True
    )
    if automated is not None:
        return automated

    container = get_active_container()
    return await _handle_lock_frozen(
        payload,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
    )


async def handle_lock_unfrozen(payload: dict) -> dict:
    automated = await _handle_with_automations(
        payload, EVENT_CHASTER_LOCK_UNFROZEN, frozen=False
    )
    if automated is not None:
        return automated

    container = get_active_container()
    return await _handle_lock_unfrozen(
        payload,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
    )


def _session_fields_from_payload(payload: dict) -> dict:
    """Best-effort session metadata from an extension_session webhook."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    session_data = data.get("session")
    if not isinstance(session_data, dict):
        return {}

    lock = session_data.get("lock")
    lock_data = lock if isinstance(lock, dict) else {}
    keyholder = lock_data.get("keyholder")
    wearer = lock_data.get("user")
    config = session_data.get("config")
    if not isinstance(config, dict):
        config = data.get("config")

    return {
        "lock_id": lock_data.get("_id") if isinstance(lock_data.get("_id"), str) else None,
        "keyholder_id": (
            keyholder.get("_id")
            if isinstance(keyholder, dict) and isinstance(keyholder.get("_id"), str)
            else None
        ),
        "wearer_id": (
            wearer.get("_id")
            if isinstance(wearer, dict) and isinstance(wearer.get("_id"), str)
            else None
        ),
        "config": ChasterExtensionConfigSchema(
            **(config if isinstance(config, dict) else {})
        ),
    }


async def handle_extension_session_joined(payload: dict) -> dict:
    """Handle the Chaster extension_session.created event."""
    container = get_active_container()
    session_id = extract_session_id(payload)
    if not session_id:
        return {"status": "ok", "action": "session_joined_ignored_no_session"}

    fields = _session_fields_from_payload(payload)
    session = await container.session_repository.get_by_session_id(session_id)
    if session is None:
        session = await container.session_repository.get_or_create(
            session_id,
            config=fields.pop("config", ChasterExtensionConfigSchema()),
            **fields,
        )
    else:
        # A configuration page can create the local row before the session
        # page provides the Chaster identities. Fill missing metadata now.
        updates = {
            key: value
            for key, value in fields.items()
            if key != "config"
            and value is not None
            and getattr(session, key, None) is None
        }
        if updates:
            await container.session_repository.update(session_id, **updates)
            for key, value in updates.items():
                setattr(session, key, value)

    try:
        event_id = build_event_key(payload) or payload.get("requestId")
    except (TypeError, ValueError):
        event_id = payload.get("requestId")
    if not event_id:
        event_id = f"{EVENT_CHASTER_SESSION_JOINED}:{session_id}"

    executions = await container.automation_engine.evaluate_event(
        session,
        event_type=EVENT_CHASTER_SESSION_JOINED,
        payload=payload,
        context={"chaster_frozen": False},
        event_id=str(event_id),
    )
    return {
        "status": "ok",
        "action": "session_joined_processed",
        "executions": len(executions),
    }


async def handle_extension_session_deleted(payload: dict) -> dict:
    container = get_active_container()
    session_id = extract_session_id(payload)
    if session_id:
        # Give "session left" rules a chance to unlock PuryFi before the
        # connection, queue and configuration are purged.
        try:
            await _handle_with_automations(
                payload, EVENT_CHASTER_SESSION_LEFT, frozen=False
            )
        except Exception:  # noqa: BLE001 - never block the Chaster cleanup
            import structlog

            structlog.get_logger(__name__).exception(
                "automation.session_left_failed", session_id=session_id
            )

        # Keep a non-active archive for 30 days so the creator can duplicate
        # the rules into a future lock.
        try:
            await container.automation_engine.archive_session(session_id)
        except Exception:  # noqa: BLE001 - never block the Chaster cleanup
            import structlog

            structlog.get_logger(__name__).exception(
                "automation.archive_failed", session_id=session_id
            )

    return await _handle_extension_session_deleted(
        payload,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
        watchers=container.session_watchers,
    )


async def handle_extension_updated(payload: dict) -> dict:
    return await _handle_extension_updated(payload)


__all__ = [
    "handle_extension_session_deleted",
    "handle_extension_session_joined",
    "handle_extension_updated",
    "handle_lock_frozen",
    "handle_lock_unfrozen",
]
