from typing import Any, Self

from models.connection import Connection
from models.documents.user_lock_configuration import UserLockConfiguration
from models.session_watchers import watchers
from schemas import ChasterExtensionConfigSchema


class ConnectionManager:
    _instance: "ConnectionManager | None" = None
    _connections: dict[str, Connection]

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections = {}
        return cls._instance

    @property
    def connections(self) -> list[Connection]:
        return list(self._connections.values())

    async def add(self, connection: Connection, user_link_token: str) -> None:
        self._connections[user_link_token] = connection
        await self.publish_status(connection)

    async def remove(self, user_link_token: str, connection: Connection | None = None) -> None:
        current = self._connections.get(user_link_token)
        if current is None:
            return

        # A new Puryfi connection can replace the previous one for the same
        # token before the old socket finishes closing. Only the connection
        # that is still registered may take itself down.
        if connection is not None and current is not connection:
            return

        self._connections.pop(user_link_token, None)
        await self.publish_status(connection or current)

    def get_by_user_link_token(self, user_link_token: str) -> Connection | None:
        return self._connections.get(user_link_token)

    async def close_by_user_link_token(
        self, user_link_token: str, code: int = 1000
    ) -> bool:
        """Revoke a plugin connection and tell watchers it is offline."""
        connection = self._connections.pop(user_link_token, None)
        if connection is None:
            return False

        # Publish before closing the watchers: the session lifecycle handler
        # closes them right afterwards.
        await self.publish_status(connection)
        await connection.close(code=code)
        return True

    def status_for_lock_config(self, lock_config: UserLockConfiguration) -> dict[str, Any]:
        """Current Puryfi link status, shaped for the extension UI sockets."""
        return {
            "type": "status",
            "is_online": self.get_by_user_link_token(lock_config.link_token or "") is not None,
            "has_linked_plugin": lock_config.has_linked_plugin,
        }

    async def publish_status(self, connection: Connection) -> None:
        """Push the current status to every browser watching this session."""
        session_id = connection.user_lock_config.session_id
        if not session_id:
            return

        await watchers.broadcast(
            session_id,
            self.status_for_lock_config(connection.user_lock_config),
        )

    def update_cached_config(self, user_link_token: str, config: ChasterExtensionConfigSchema) -> None:
        """Update the in-memory config of a live connection (REVIEW.md #17:
        this does not push anything to the Puryfi client — it only refreshes
        what the server-side handlers see for this connection)."""
        connection = self.get_by_user_link_token(user_link_token)
        if connection:
            connection.user_lock_config.config = config

manager = ConnectionManager()
