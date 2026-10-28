from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionConfigSchema


async def get_or_create_lock_configuration(
    session_id: str,
    *,
    config: ChasterExtensionConfigSchema | dict[str, Any],
    **fields: Any,
) -> UserLockConfiguration:
    """Atomically fetch or create the configuration for a Chaster session.

    The previous `find_one` + `insert` sequence had a race: two concurrent
    iframe/config requests could both see no document and insert two configs.
    `find_one_and_update(..., upsert=True)` relies on the unique `session_id`
    index and applies `$setOnInsert` only when the document does not exist.

    If MongoDB still reports a duplicate key (two concurrent upserts), the
    winning document is read back and returned.
    """
    if isinstance(config, dict):
        config = ChasterExtensionConfigSchema(**config)

    insert_fields = {
        "session_id": session_id,
        "config": config.model_dump(),
        **fields,
    }
    collection = UserLockConfiguration.get_pymongo_collection()

    try:
        document = await collection.find_one_and_update(
            {"session_id": session_id},
            {"$setOnInsert": insert_fields},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        # Concurrent upsert won the race; read the document it created.
        document = await collection.find_one({"session_id": session_id})

    if document is None:
        raise RuntimeError(
            f"UserLockConfiguration for session {session_id!r} is missing after upsert"
        )

    return UserLockConfiguration.model_validate(document)
