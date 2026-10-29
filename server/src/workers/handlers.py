"""Webhook handlers bound to the active application container.

Keeping the dependency wiring here means the domain use cases stay pure while
the worker (and the legacy ``routes.webhooks.actions`` import path) sees simple
``handler(payload)`` callables. The container is resolved at call time so a
fresh app instance (tests, embedded usage) never reuses stale adapters.
"""

from container import get_active_container
from domain.use_cases.lock_events import (
    handle_extension_updated as _handle_extension_updated,
)
from domain.use_cases.lock_events import handle_lock_frozen as _handle_lock_frozen
from domain.use_cases.lock_events import handle_lock_unfrozen as _handle_lock_unfrozen
from domain.use_cases.session_lifecycle import (
    handle_extension_session_deleted as _handle_extension_session_deleted,
)


async def handle_lock_frozen(payload: dict) -> dict:
    container = get_active_container()
    return await _handle_lock_frozen(
        payload,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
    )


async def handle_lock_unfrozen(payload: dict) -> dict:
    container = get_active_container()
    return await _handle_lock_unfrozen(
        payload,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
    )


async def handle_extension_session_deleted(payload: dict) -> dict:
    container = get_active_container()
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
    "handle_extension_updated",
    "handle_lock_frozen",
    "handle_lock_unfrozen",
]
