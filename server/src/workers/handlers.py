"""Webhook handlers bound to the process composition root.

Keeping the dependency wiring here means the domain use cases stay pure while
the worker (and the legacy ``routes.webhooks.actions`` import path) sees simple
``handler(payload)`` callables.
"""

from container import (
    message_queue,
    puryfi_registry,
    session_repository,
    session_watchers,
)
from domain.use_cases.lock_events import (
    handle_extension_updated as _handle_extension_updated,
)
from domain.use_cases.lock_events import handle_lock_frozen as _handle_lock_frozen
from domain.use_cases.lock_events import handle_lock_unfrozen as _handle_lock_unfrozen
from domain.use_cases.session_lifecycle import (
    handle_extension_session_deleted as _handle_extension_session_deleted,
)


async def handle_lock_frozen(payload: dict) -> dict:
    return await _handle_lock_frozen(
        payload,
        sessions=session_repository,
        queue=message_queue,
        puryfi=puryfi_registry,
    )


async def handle_lock_unfrozen(payload: dict) -> dict:
    return await _handle_lock_unfrozen(
        payload,
        sessions=session_repository,
        queue=message_queue,
        puryfi=puryfi_registry,
    )


async def handle_extension_session_deleted(payload: dict) -> dict:
    return await _handle_extension_session_deleted(
        payload,
        sessions=session_repository,
        queue=message_queue,
        puryfi=puryfi_registry,
        watchers=session_watchers,
    )


async def handle_extension_updated(payload: dict) -> dict:
    return await _handle_extension_updated(payload)


__all__ = [
    "handle_extension_session_deleted",
    "handle_extension_updated",
    "handle_lock_frozen",
    "handle_lock_unfrozen",
]
