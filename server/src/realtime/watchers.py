import asyncio
from typing import Any

from fastapi import WebSocket

from infra.logging import get_logger

log = get_logger(__name__)

WATCHER_SEND_TIMEOUT_SECONDS = 5.0


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

    async def _send(
        self, session_id: str, websocket: WebSocket, message: dict[str, Any]
    ) -> None:
        try:
            await asyncio.wait_for(
                websocket.send_json(message),
                timeout=WATCHER_SEND_TIMEOUT_SECONDS,
            )
        except Exception:
            log.debug("watcher.send_failed", session_id=session_id, exc_info=True)
            self.remove(session_id, websocket)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        # Fan out concurrently so one slow watcher cannot block the others.
        targets = list(self._watchers.get(session_id, ()))
        await asyncio.gather(
            *(self._send(session_id, websocket, message) for websocket in targets)
        )

    async def close_session(self, session_id: str, code: int = 1000) -> None:
        """Close every browser socket watching a session that no longer exists."""
        for websocket in self._watchers.pop(session_id, set()):
            try:
                await websocket.close(code=code)
            except Exception:
                log.debug("watcher.close_failed", session_id=session_id, exc_info=True)


watchers = SessionWatcherManager()
