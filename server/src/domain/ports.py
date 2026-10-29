"""Ports implemented by the infrastructure, realtime and worker layers.

The domain use cases only depend on these protocols, never on FastAPI,
Beanie, msgpack or a concrete database client.
"""

import asyncio
from typing import Any, Protocol

from domain.entities import (
    ChasterConfiguration,
    ChasterExtensionConfigSchema,
    ChasterSessionAuth,
    LockSession,
    QueuedCommand,
)


class LockSessionRepository(Protocol):
    async def get_or_create(
        self,
        session_id: str,
        *,
        config: ChasterExtensionConfigSchema,
        **fields: Any,
    ) -> LockSession: ...

    async def get_by_session_id(self, session_id: str) -> LockSession | None: ...

    async def get_by_link_token(self, link_token: str) -> LockSession | None: ...

    async def update(self, session_id: str, **fields: Any) -> bool: ...

    async def delete(self, session_id: str) -> bool: ...

    async def mark_linked(self, link_token: str) -> bool: ...

    async def increment_censored_count(self, session_id: str) -> int | None: ...

    async def reset_censored_count(self, session_id: str) -> None: ...


class MessageQueue(Protocol):
    async def enqueue(
        self, link_token: str, msg_type: str, payload: dict[str, Any]
    ) -> None: ...

    async def fetch(self, link_token: str) -> list[QueuedCommand]: ...

    async def delete(self, command: QueuedCommand) -> None: ...

    async def delete_for_token(self, link_token: str) -> None: ...


class ChasterGateway(Protocol):
    async def get_session_auth(self, main_token: str) -> ChasterSessionAuth: ...

    async def get_configuration(
        self, configuration_token: str
    ) -> ChasterConfiguration: ...

    async def update_configuration(
        self,
        configuration_token: str,
        config: ChasterExtensionConfigSchema,
    ) -> str | None: ...

    async def add_time(self, session_id: str, duration: int) -> bool: ...

    async def create_log(
        self,
        session_id: str,
        *,
        role: str,
        title: str,
        description: str,
        icon: str = "link",
        color: str = "#ffffff",
    ) -> bool: ...


class PuryfiConnection(Protocol):
    """The subset of a live Puryfi connection used by the domain use cases.

    ``ready`` reflects the plugin handshake, while ``intents_granted`` reflects
    the permission grant required before sending protected messages. Both must
    be true before ``flush_queue`` can deliver anything.
    """

    @property
    def ready(self) -> bool: ...

    @property
    def intents_granted(self) -> bool: ...

    async def send_message(self, msg_type: str, payload: dict) -> dict: ...

    async def send_messages(
        self, messages: list[tuple[str, dict]]
    ) -> list[dict]: ...

    async def flush_queue(self) -> bool:
        """Deliver durable commands if ready and granted; True when fully drained."""
        ...


class PuryfiRegistry(Protocol):
    def get(self, user_link_token: str) -> PuryfiConnection | None: ...

    def is_online(self, user_link_token: str) -> bool: ...

    def get_version(self, user_link_token: str) -> str | None: ...

    async def close_by_user_link_token(
        self, user_link_token: str, code: int = 1000
    ) -> bool: ...

    async def update_cached_config(
        self, user_link_token: str, config: ChasterExtensionConfigSchema
    ) -> None: ...


class SessionWatchers(Protocol):
    async def close_session(self, session_id: str, code: int = 1000) -> None: ...


class OutboundConnection(Protocol):
    """The subset of a live Puryfi connection used by the outbound worker."""

    intents_granted_event: asyncio.Event

    @property
    def intents_granted(self) -> bool: ...

    async def send_message(self, msg_type: str, payload: dict) -> dict: ...

    async def on_linked(self, session: LockSession) -> None: ...
