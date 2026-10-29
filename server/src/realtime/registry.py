"""In-process registry of live Puryfi plugin connections."""

import asyncio
from typing import Any, Self, cast

from domain.entities import ChasterExtensionConfigSchema, LockSession
from infra.logging import get_logger
from infra.redaction import token_fingerprint
from realtime.connection import Connection
from realtime.watchers import watchers

log = get_logger(__name__)


class ConnectionManager:
    _instance: "ConnectionManager | None" = None
    _connections: dict[str, Connection]
    _locks: dict[str, asyncio.Lock]

    def __new__(cls) -> Self:
        instance = cls._instance
        if instance is None:
            instance = super().__new__(cls)
            instance._connections = {}
            instance._locks = {}
            cls._instance = instance
        return cast(Self, instance)

    def _lock_for(self, user_link_token: str) -> asyncio.Lock:
        return self._locks.setdefault(user_link_token, asyncio.Lock())

    @property
    def connections(self) -> list[Connection]:
        return list(self._connections.values())

    async def add(self, connection: Connection, user_link_token: str) -> None:
        """Register a connection, replacing and closing any previous one."""
        # The connection publishes status changes through this registry, which
        # removes the old import cycle between Connection and ConnectionManager.
        set_publisher = getattr(connection, "set_status_publisher", None)
        if set_publisher is not None:
            set_publisher(self.publish_status)

        async with self._lock_for(user_link_token):
            previous = self._connections.get(user_link_token)
            self._connections[user_link_token] = connection

        if previous is None or previous is connection:
            return

        # A new socket for the same token must win: the old one could still
        # process scans or receive RPC responses. Replace it explicitly.
        log.info(
            "connection.replaced",
            link_token=token_fingerprint(user_link_token),
        )
        await self.publish_status(connection)
        await previous.close(code=4001)

    async def remove(
        self, user_link_token: str, connection: Connection | None = None
    ) -> None:
        async with self._lock_for(user_link_token):
            current = self._connections.get(user_link_token)
            if current is None:
                return

            # Only the connection that is still registered may take itself
            # down: a replacement may already own the slot.
            if connection is not None and current is not connection:
                return

            self._connections.pop(user_link_token, None)

        await self.publish_status(connection or current)

    def get_by_user_link_token(self, user_link_token: str) -> Connection | None:
        return self._connections.get(user_link_token)

    # Domain-friendly alias matching the PuryfiRegistry port.
    def get(self, user_link_token: str) -> Connection | None:
        return self.get_by_user_link_token(user_link_token)

    def is_online(self, user_link_token: str) -> bool:
        """A connection is online only once it completed the `ready` handshake."""
        connection = self._connections.get(user_link_token)
        return connection is not None and connection.ready

    async def close_by_user_link_token(
        self, user_link_token: str, code: int = 1000
    ) -> bool:
        """Revoke a plugin connection and tell watchers it is offline."""
        async with self._lock_for(user_link_token):
            connection = self._connections.pop(user_link_token, None)

        if connection is None:
            return False

        # Publish before closing the watchers: the session lifecycle handler
        # closes them right afterwards.
        await self.publish_status(connection)
        await connection.close(code=code)
        return True

    def status_for_lock_config(self, lock_config: LockSession) -> dict[str, Any]:
        """Current Puryfi link status, shaped for the extension UI sockets."""
        return {
            "type": "status",
            "is_online": self.is_online(lock_config.link_token or ""),
            "has_linked_plugin": lock_config.has_linked_plugin,
        }

    # Domain-friendly alias.
    def status_for_session(self, session: LockSession) -> dict[str, Any]:
        return self.status_for_lock_config(session)

    async def publish_status(self, connection: Connection) -> None:
        """Push the current status to every browser watching this session."""
        lock_config = getattr(connection, "session", None) or getattr(
            connection, "user_lock_config", None
        )
        if lock_config is None:
            return

        session_id = lock_config.session_id
        if not session_id:
            return

        await watchers.broadcast(
            session_id,
            self.status_for_lock_config(lock_config),
        )

    async def update_cached_config(
        self, user_link_token: str, config: ChasterExtensionConfigSchema
    ) -> None:
        """Update the in-memory config of a live connection.

        This does not push anything to the Puryfi client: it only refreshes
        what the server-side handlers see for this connection.
        """
        connection = self.get_by_user_link_token(user_link_token)
        if connection:
            await connection.update_configuration(config)


manager = ConnectionManager()
