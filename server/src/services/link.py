from beanie.exceptions import CollectionWasNotInitialized
from pymongo.errors import PyMongoError

from models.documents.user_lock_configuration import UserLockConfiguration
from utils.logging_config import get_logger
from utils.redaction import token_fingerprint

log = get_logger(__name__)


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
            log.warning(
                "link.no_configuration",
                link_token=token_fingerprint(link_token),
            )
            return False

        lock_config.has_linked_plugin = True
        await lock_config.save()

        log.info(
            "link.linked",
            session_id=str(lock_config.id),
            link_token=token_fingerprint(link_token),
        )

        return True

    except (CollectionWasNotInitialized, PyMongoError):
        log.warning(
            "link.failed",
            link_token=token_fingerprint(link_token),
            exc_info=True,
        )
        return False
