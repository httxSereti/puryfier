"""Deprecated service facade. Use :class:`infra.repositories.MongoLockSessionRepository`."""

from typing import Any

from container import get_active_container
from domain.entities import ChasterExtensionConfigSchema, LockSession


async def get_or_create_lock_configuration(
    session_id: str,
    *,
    config: ChasterExtensionConfigSchema | dict[str, Any],
    **fields: Any,
) -> LockSession:
    if isinstance(config, dict):
        config = ChasterExtensionConfigSchema(**config)
    return await get_active_container().session_repository.get_or_create(session_id, config=config, **fields)
