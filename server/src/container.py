"""Composition root for a Puryfier application instance.

The container owns every process-wide dependency and is attached to
``app.state.container`` by the application factory. The module-level
``get_active_container()`` helper exists only for the deprecated service
facades and the webhook handler module while they are migrated; new code must
receive dependencies explicitly or read them from ``app.state``.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import Settings, get_settings
from domain.ports import (
    ChasterGateway,
    LockSessionRepository,
    MessageQueue,
)
from domain.use_cases.media_scan import MediaScanService
from infra.chaster import ChasterService
from infra.queue import MongoMessageQueue
from infra.repositories import MongoLockSessionRepository
from realtime.registry import ConnectionManager, manager
from realtime.watchers import SessionWatcherManager, watchers
from workers.webhook_inbox import WebhookInboxWorker, webhook_worker


@dataclass(slots=True)
class Container:
    """Dependencies bound to one application instance."""

    settings: Settings
    chaster_gateway: ChasterGateway
    session_repository: LockSessionRepository
    message_queue: MessageQueue
    puryfi_registry: ConnectionManager
    session_watchers: SessionWatcherManager
    media_scans: MediaScanService
    webhook_worker: WebhookInboxWorker


_active_container: Container | None = None


def build_container(settings: Settings | None = None) -> Container:
    """Build the composition root from validated settings.

    Repositories and the queue are stateless Beanie adapters. The realtime
    registry and watcher manager remain process-wide singletons: the app is
    explicitly single-worker until the Redis bus from P3 lands.
    """
    settings = settings or get_settings()

    chaster_gateway = ChasterService()
    session_repository = MongoLockSessionRepository()
    message_queue = MongoMessageQueue()

    return Container(
        settings=settings,
        chaster_gateway=chaster_gateway,
        session_repository=session_repository,
        message_queue=message_queue,
        puryfi_registry=manager,
        session_watchers=watchers,
        media_scans=MediaScanService(
            sessions=session_repository,
            chaster=chaster_gateway,
        ),
        webhook_worker=webhook_worker,
    )


def set_active_container(container: Container) -> None:
    """Bind the container used by legacy facades for the current app."""
    global _active_container
    _active_container = container


def get_active_container() -> Container:
    """Return the active container, building a default one if needed.

    Applications normally set it in ``create_app``/lifespan. The fallback
    keeps direct unit tests and the deprecated service facades working.
    """
    global _active_container
    if _active_container is None:
        _active_container = build_container()
    return _active_container


_LEGACY_EXPORTS = {
    "chaster_gateway",
    "media_scans",
    "message_queue",
    "puryfi_registry",
    "session_repository",
    "session_watchers",
    "settings",
    "webhook_worker",
}


def __getattr__(name: str):
    """Compatibility for ``from container import session_repository``."""
    if name in _LEGACY_EXPORTS:
        return getattr(get_active_container(), name)
    raise AttributeError(name)


__all__ = [
    "Container",
    "build_container",
    "get_active_container",
    "set_active_container",
]
