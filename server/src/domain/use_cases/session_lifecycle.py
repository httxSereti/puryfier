"""Session revocation and deletion use cases."""

import structlog

from domain.events import extract_session_id
from domain.ports import (
    LockSessionRepository,
    MessageQueue,
    PuryfiRegistry,
    SessionWatchers,
)
from domain.redaction import token_fingerprint

log = structlog.get_logger(__name__)

# Custom WebSocket close code used for a revoked/ended session.
SESSION_ENDED_CLOSE_CODE = 4004


async def revoke_session(
    session_id: str,
    *,
    sessions: LockSessionRepository,
    queue: MessageQueue,
    puryfi: PuryfiRegistry,
    watchers: SessionWatchers,
) -> bool:
    """Purge a Chaster session and revoke access to its Puryfi link.

    Closes the plugin connection and every browser watcher, deletes queued
    messages, then deletes the configuration. Deleting the configuration makes
    the old link token unusable: any reconnection attempt fails the lookup.
    """
    session = await sessions.get_by_session_id(session_id)

    if session is None:
        # A watcher could still be open if the config disappeared earlier.
        await watchers.close_session(session_id, code=SESSION_ENDED_CLOSE_CODE)
        return False

    if session.link_token:
        await puryfi.close_by_user_link_token(
            session.link_token, code=SESSION_ENDED_CLOSE_CODE
        )
        await queue.delete_for_token(session.link_token)
        log.info(
            "session.revoked",
            session_id=session_id,
            link_token=token_fingerprint(session.link_token),
        )

    await watchers.close_session(session_id, code=SESSION_ENDED_CLOSE_CODE)
    await sessions.delete(session_id)
    log.info("session.purged", session_id=session_id)
    return True


async def handle_extension_session_deleted(
    payload: dict,
    *,
    sessions: LockSessionRepository,
    queue: MessageQueue,
    puryfi: PuryfiRegistry,
    watchers: SessionWatchers,
) -> dict:
    """Purge everything tied to a Chaster session that has ended."""
    session_id = extract_session_id(payload)
    if not session_id:
        log.warning("webhook.session_deleted.no_session")
        return {
            "status": "ok",
            "action": "extension_session_deleted_ignored_no_session",
        }

    deleted = await revoke_session(
        session_id,
        sessions=sessions,
        queue=queue,
        puryfi=puryfi,
        watchers=watchers,
    )
    if not deleted:
        return {
            "status": "ok",
            "action": "extension_session_deleted_ignored_no_config",
        }

    return {"status": "ok", "action": "extension_session_deleted_processed"}
