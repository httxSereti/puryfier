from models.connection_manager import manager
from models.documents import QueuedMessage, UserLockConfiguration
from models.session_watchers import watchers
from utils.logging_config import get_logger
from utils.redaction import token_fingerprint

log = get_logger(__name__)

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
        log.info(
            "session.revoked",
            session_id=session_id,
            link_token=token_fingerprint(link_token),
        )

    await watchers.close_session(session_id, code=SESSION_ENDED_CLOSE_CODE)
    await lock_config.delete()
    log.info("session.purged", session_id=session_id)
    return True
