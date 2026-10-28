import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class SessionWatcherManager:
    """Tracks browser sockets watching the realtime status of a lock session."""

    def __init__(self) -> None:
        self._watchers: dict[str, set[WebSocket]] = {}

    def add(self, session_id: str, websocket: WebSocket) -> None:
        self._watchers.setdefault(session_id, set()).add(websocket)

    def remove(self, session_id: str, websocket: WebSocket) -> None:
        watchers = self._watchers.get(session_id)
        if watchers is None:
            return

        watchers.discard(websocket)
        if not watchers:
            self._watchers.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        # Copy the set: a failed send removes the watcher while we iterate.
        for websocket in list(self._watchers.get(session_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - a dead watcher must not break the fan-out
                self.remove(session_id, websocket)

    async def close_session(self, session_id: str, code: int = 1000) -> None:
        """Close every browser socket watching a session that no longer exists."""
        for websocket in self._watchers.pop(session_id, set()):
            try:
                await websocket.close(code=code)
            except Exception:
                logger.debug("Failed to close session watcher", exc_info=True)


watchers = SessionWatcherManager()
