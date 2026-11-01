"""Mongo implementations for automation storage and execution audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import UpdateOne

from infra.documents.automation import Automation, AutomationExecution, MediaCounter


def _object_id(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


class MongoAutomationRepository:
    """Persistent automation rules, scoped to one Chaster session."""

    async def create(self, fields: dict[str, Any]) -> Automation:
        document = Automation(**fields)
        await document.insert()
        return document

    async def get(self, automation_id: str) -> Automation | None:
        object_id = _object_id(automation_id)
        if object_id is None:
            return None
        return await Automation.get(object_id)

    async def list_for_session(
        self, session_id: str, *, include_archived: bool = False
    ) -> list[Automation]:
        query: dict[str, Any] = {"session_id": session_id}
        if not include_archived:
            query["status"] = "active"
        return await Automation.find(query).sort("+priority", "+created_at").to_list()

    async def list_archived_for_owner(
        self, owner_id: str, *, limit: int = 50
    ) -> list[Automation]:
        return (
            await Automation.find(
                {"owner_id": owner_id, "status": "archived"}
            )
            .sort("-archived_at")
            .limit(limit)
            .to_list()
        )

    async def list_for_owner(
        self, owner_id: str, *, include_archived: bool = False
    ) -> list[Automation]:
        query: dict[str, Any] = {"owner_id": owner_id}
        if not include_archived:
            query["status"] = "active"
        return await Automation.find(query).sort("+priority", "+created_at").to_list()

    async def update(
        self, automation_id: str, **fields: Any
    ) -> Automation | None:
        object_id = _object_id(automation_id)
        if object_id is None:
            return None

        fields["updated_at"] = datetime.now(UTC)
        document = await Automation.get_pymongo_collection().find_one_and_update(
            {"_id": object_id},
            {"$set": fields},
            return_document=True,
        )
        if document is None:
            return None
        return Automation.model_validate(document)

    async def delete(self, automation_id: str) -> bool:
        object_id = _object_id(automation_id)
        if object_id is None:
            return False
        result = await Automation.get_pymongo_collection().delete_one(
            {"_id": object_id}
        )
        return result.deleted_count > 0

    async def archive_for_session(self, session_id: str) -> int:
        now = datetime.now(UTC)
        result = await Automation.get_pymongo_collection().update_many(
            {"session_id": session_id, "status": "active"},
            {
                "$set": {
                    "status": "archived",
                    "enabled": False,
                    "archived_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    async def has_active_for_session(self, session_id: str) -> bool:
        document = await Automation.get_pymongo_collection().find_one(
            {"session_id": session_id, "status": "active"},
            {"_id": 1},
        )
        return document is not None

    async def count_active_for_owner(self, owner_id: str) -> int:
        return await Automation.find(
            {"owner_id": owner_id, "status": "active"}
        ).count()


class MongoMediaCounterRepository:
    """Per-rule media counters, flushed in batches by the scan engine."""

    async def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return await MediaCounter.get_pymongo_collection().find(
            {"session_id": session_id}
        ).to_list()

    async def bulk_upsert(self, counters: list[dict[str, Any]]) -> None:
        if not counters:
            return

        operations = [
            UpdateOne(
                {
                    "session_id": counter["session_id"],
                    "automation_id": counter["automation_id"],
                },
                {"$set": counter},
                upsert=True,
            )
            for counter in counters
        ]
        await MediaCounter.get_pymongo_collection().bulk_write(
            operations, ordered=False
        )

    async def delete_for_session(self, session_id: str) -> None:
        await MediaCounter.get_pymongo_collection().delete_many(
            {"session_id": session_id}
        )

    async def delete_for_automation(
        self, session_id: str, automation_id: str
    ) -> None:
        await MediaCounter.get_pymongo_collection().delete_one(
            {"session_id": session_id, "automation_id": automation_id}
        )


class MongoAutomationExecutionRepository:
    """Audit trail for automation runs."""

    async def create(self, fields: dict[str, Any]) -> AutomationExecution:
        document = AutomationExecution(**fields)
        await document.insert()
        return document

    async def update(
        self, execution_id: str, **fields: Any
    ) -> AutomationExecution | None:
        object_id = _object_id(execution_id)
        if object_id is None:
            return None
        document = await AutomationExecution.get_pymongo_collection().find_one_and_update(
            {"_id": object_id},
            {"$set": fields},
            return_document=True,
        )
        if document is None:
            return None
        return AutomationExecution.model_validate(document)

    async def list_for_session(
        self, session_id: str, *, limit: int = 25
    ) -> list[AutomationExecution]:
        return (
            await AutomationExecution.find({"session_id": session_id})
            .sort("-started_at")
            .limit(limit)
            .to_list()
        )
