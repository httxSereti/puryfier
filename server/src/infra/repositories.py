"""Mongo/Beanie implementations of the domain repositories."""

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from domain.entities import ChasterExtensionConfigSchema, LockSession
from infra.documents import UserLockConfiguration


def _to_entity(document: dict[str, Any] | UserLockConfiguration) -> LockSession:
    if isinstance(document, UserLockConfiguration):
        raw = document.model_dump()
        raw_id = document.id
    else:
        raw = document
        raw_id = raw.get("_id")

    config = raw.get("config") or {}
    if not isinstance(config, ChasterExtensionConfigSchema):
        config = ChasterExtensionConfigSchema(**config)

    return LockSession(
        id=str(raw_id) if raw_id is not None else None,
        session_id=raw["session_id"],
        lock_id=raw.get("lock_id"),
        link_token=raw.get("link_token"),
        has_linked_plugin=bool(raw.get("has_linked_plugin", False)),
        keyholder_id=raw.get("keyholder_id"),
        wearer_id=raw.get("wearer_id"),
        puryfi_username=raw.get("puryfi_username"),
        seen_censored_objects=int(raw.get("seen_censored_objects", 0) or 0),
        lock_password=raw.get("lock_password"),
        config=config,
    )


class MongoLockSessionRepository:
    """Beanie-backed implementation of ``LockSessionRepository``."""

    @property
    def _collection(self):
        return UserLockConfiguration.get_pymongo_collection()

    async def get_or_create(
        self,
        session_id: str,
        *,
        config: ChasterExtensionConfigSchema,
        **fields: Any,
    ) -> LockSession:
        insert_fields = {
            "session_id": session_id,
            "config": config.model_dump(),
            **fields,
        }

        try:
            document = await self._collection.find_one_and_update(
                {"session_id": session_id},
                {"$setOnInsert": insert_fields},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Concurrent upsert won the race; read the document it created.
            document = await self._collection.find_one({"session_id": session_id})

        if document is None:
            raise RuntimeError(
                f"UserLockConfiguration for session {session_id!r} is missing after upsert"
            )

        return _to_entity(document)

    async def get_by_session_id(self, session_id: str) -> LockSession | None:
        document = await self._collection.find_one({"session_id": session_id})
        return _to_entity(document) if document is not None else None

    async def get_by_link_token(self, link_token: str) -> LockSession | None:
        document = await self._collection.find_one({"link_token": link_token})
        return _to_entity(document) if document is not None else None

    async def update(self, session_id: str, **fields: Any) -> bool:
        if not fields:
            return True

        update_fields = dict(fields)
        config = update_fields.get("config")
        if isinstance(config, ChasterExtensionConfigSchema):
            update_fields["config"] = config.model_dump()

        result = await self._collection.update_one(
            {"session_id": session_id}, {"$set": update_fields}
        )
        return result.matched_count > 0

    async def delete(self, session_id: str) -> bool:
        result = await self._collection.delete_one({"session_id": session_id})
        return result.deleted_count > 0

    async def mark_linked(self, link_token: str) -> bool:
        """Atomically transition ``has_linked_plugin`` from false to true."""
        result = await self._collection.update_one(
            {"link_token": link_token, "has_linked_plugin": {"$ne": True}},
            {"$set": {"has_linked_plugin": True}},
        )
        return result.modified_count > 0

    async def increment_censored_count(self, session_id: str) -> int | None:
        return await self.increment_censored_count_by(session_id, 1)

    async def increment_censored_count_by(
        self, session_id: str, count: int
    ) -> int | None:
        """Atomically add ``count`` censored images and return the new total."""
        if count < 0:
            raise ValueError("count must be non-negative")

        if count == 0:
            document = await self._collection.find_one({"session_id": session_id})
        else:
            document = await self._collection.find_one_and_update(
                {"session_id": session_id},
                {"$inc": {"seen_censored_objects": count}},
                return_document=ReturnDocument.AFTER,
            )

        if isinstance(document, dict) and isinstance(
            document.get("seen_censored_objects"), int
        ):
            return document["seen_censored_objects"]
        return None

    async def claim_censored_penalties(
        self,
        session_id: str,
        limit: int,
        max_penalties: int,
    ) -> int:
        """Atomically claim whole thresholds and return the claimed image count.

        Claiming decrements the persisted counter by ``limit * k``. If another
        flush already claimed the same block, nothing is returned and no
        penalty may be applied.
        """
        if limit <= 0 or max_penalties <= 0:
            return 0

        claimed = limit * max_penalties
        document = await self._collection.find_one_and_update(
            {
                "session_id": session_id,
                "seen_censored_objects": {"$gte": claimed},
            },
            {"$inc": {"seen_censored_objects": -claimed}},
            return_document=ReturnDocument.AFTER,
        )
        return claimed if document is not None else 0

    async def restore_censored_count(self, session_id: str, count: int) -> None:
        """Give back a claimed block after the Chaster call failed."""
        if count <= 0:
            return
        await self._collection.update_one(
            {"session_id": session_id},
            {"$inc": {"seen_censored_objects": count}},
        )

    async def reset_censored_count(self, session_id: str) -> None:
        await self._collection.update_one(
            {"session_id": session_id},
            {"$set": {"seen_censored_objects": 0}},
        )
