from models.connection_manager import manager
from models.documents import QueuedMessage, UserLockConfiguration
from models.session_watchers import watchers
from utils.redaction import token_fingerprint

# Custom WebSocket close code used for a revoked/ended session.
SESSION_ENDED_CLOSE_CODE = 4004


async def revoke_session(session_id: str) -> bool:
    """Purge a Chaster session and revoke access to its Puryfi link.

    Closes the plugin connection and every browser watcher, deletes queued
    messages, then deletes the configuration. Deleting the configuration makes
    the old link token unusable: any reconnection attempt fails the lookup.
    """
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )

    if lock_config is None:
        # A watcher could still be open if the config disappeared earlier.
        await watchers.close_session(session_id, code=SESSION_ENDED_CLOSE_CODE)
        return False

    link_token = lock_config.link_token
    if link_token:
        await manager.close_by_user_link_token(
            link_token, code=SESSION_ENDED_CLOSE_CODE
        )
        await QueuedMessage.find(QueuedMessage.link_token == link_token).delete()
        print(
            "[Session] Revoked Puryfi token "
            f"{token_fingerprint(link_token)} for session {session_id!r}"
        )

    await watchers.close_session(session_id, code=SESSION_ENDED_CLOSE_CODE)
    await lock_config.delete()
    print(f"[Session] Purged configuration for session {session_id!r}")
    return True
