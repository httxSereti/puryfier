"""Deprecated service facade. Use :mod:`domain.use_cases.session_lifecycle`."""

from container import (
    message_queue,
    puryfi_registry,
    session_repository,
    session_watchers,
)
from domain.use_cases.session_lifecycle import (
    SESSION_ENDED_CLOSE_CODE,
)
from domain.use_cases.session_lifecycle import (
    revoke_session as _revoke_session,
)

__all__ = ["SESSION_ENDED_CLOSE_CODE", "revoke_session"]


async def revoke_session(session_id: str) -> bool:
    return await _revoke_session(
        session_id,
        sessions=session_repository,
        queue=message_queue,
        puryfi=puryfi_registry,
        watchers=session_watchers,
    )
