"""Atomic Puryfi link transition."""

import structlog

from domain.entities import LockSession
from domain.ports import LockSessionRepository
from domain.redaction import token_fingerprint

log = structlog.get_logger(__name__)


async def link_puryfi(
    link_token: str, *, sessions: LockSessionRepository
) -> LockSession | None:
    """Mark the session as linked exactly once, atomically.

    The ``has_linked_plugin`` transition is conditional so concurrent drains
    cannot create the "linked Puryfi" log twice.
    """
    session = await sessions.get_by_link_token(link_token)
    if session is None:
        log.warning(
            "link.no_configuration",
            link_token=token_fingerprint(link_token),
        )
        return None

    changed = await sessions.mark_linked(link_token)
    session.has_linked_plugin = True

    if changed:
        log.info(
            "link.linked",
            session_id=session.session_id,
            link_token=token_fingerprint(link_token),
        )

    return session
