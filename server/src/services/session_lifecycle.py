"""Deprecated service facade. Use :mod:`domain.use_cases.session_lifecycle`."""

from container import get_active_container
from domain.use_cases.session_lifecycle import (
    SESSION_ENDED_CLOSE_CODE,
)
from domain.use_cases.session_lifecycle import (
    revoke_session as _revoke_session,
)

__all__ = ["SESSION_ENDED_CLOSE_CODE", "revoke_session"]


async def revoke_session(session_id: str) -> bool:
    container = get_active_container()
    return await _revoke_session(
        session_id,
        sessions=container.session_repository,
        queue=container.message_queue,
        puryfi=container.puryfi_registry,
        watchers=container.session_watchers,
    )
