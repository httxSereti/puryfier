from typing import Dict
from models.connection import Connection


class ConnectionManager:
    _instance: "ConnectionManager | None" = None

    def __new__(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections: Dict[str, Connection] = {}
        return cls._instance

    @property
    def connections(self) -> list[Connection]:
        return self._connections

    def add(self, connection: Connection, user_link_token: str) -> None:
        self._connections[user_link_token] = connection

    def remove(self, user_link_token: str) -> None:
        self._connections.pop(user_link_token, None)

    def get_by_user_link_token(self, user_link_token: str) -> Connection | None:
        return self._connections.get(user_link_token)

manager = ConnectionManager()
