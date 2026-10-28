from beanie.exceptions import CollectionWasNotInitialized
from pymongo.errors import PyMongoError

from models.documents.user_lock_configuration import UserLockConfiguration
from utils.redaction import token_fingerprint


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
            print(
                "[Link] No UserLockConfiguration found for token "
                f"{token_fingerprint(link_token)}"
            )
            return False

        lock_config.has_linked_plugin = True
        await lock_config.save()

        print(f"[Link] Session {lock_config.id!r} is now linked ✓")

        return True

    except (CollectionWasNotInitialized, PyMongoError) as e:
        print(f"[Link] Error during linking: {e}")
        return False
