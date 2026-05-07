from models.documents.user_lock_configuration import UserLockConfiguration
from utils.chaster_api import create_custom_log


async def link_with_token(link_token: str) -> bool:
    """
    Look up the UserLockConfiguration matching link_token and mark it as linked.
    Returns True if the link was successful, False otherwise.
    """
    try:
        lock_config = await UserLockConfiguration.find_one(
            UserLockConfiguration.link_token == link_token
        )

        if lock_config is None:
            print(f"[Link] No UserLockConfiguration found for token {link_token!r}")
            return False

        lock_config.has_linked_plugin = True
        await lock_config.save()

        session_id = lock_config.session_id

        print(f"[Link] Session {lock_config.id!r} is now linked ✓")

        # Post a custom log entry to the Chaster lock session
        if session_id:
            create_custom_log(
                session_id=session_id,
                title="Puryfi Plugin is online",
                description=f"Monitoring is now active with Puryfi.",
                icon="link",
                color="#ffffff",
            )

        return True

    except Exception as e:
        print(f"[Link] Error during linking: {e}")
        return False
