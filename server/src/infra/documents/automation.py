from datetime import UTC, datetime
from typing import Any, ClassVar

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

ARCHIVE_TTL_SECONDS = 30 * 24 * 60 * 60
COUNTER_TTL_SECONDS = 30 * 24 * 60 * 60
EXECUTION_TTL_SECONDS = 90 * 24 * 60 * 60


class Automation(Document):
    """A user-defined automation attached to exactly one Chaster session."""

    session_id: str
    lock_id: str | None = None
    lock_label: str | None = None

    owner_id: str
    owner_role: str

    name: str
    status: str = "active"  # active | archived
    enabled: bool = True
    priority: int = 100

    trigger: dict[str, Any]
    actions: list[dict[str, Any]] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)

    source_automation_id: str | None = None
    disabled_by: str | None = None
    disabled_by_role: str | None = None
    disabled_at: datetime | None = None
    archived_at: datetime | None = None

    schema_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "automations"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("session_id", ASCENDING), ("status", ASCENDING), ("enabled", ASCENDING)]
            ),
            IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)]),
            # Active automations have archived_at=None, which MongoDB's TTL
            # monitor ignores because it is not a date.
            IndexModel(
                [("archived_at", ASCENDING)],
                expireAfterSeconds=ARCHIVE_TTL_SECONDS,
            ),
        ]


class MediaCounter(Document):
    """Per-automation occurrence counter for media scans."""

    session_id: str
    automation_id: str
    occurrence_count: int = 0
    window_started_at: datetime | None = None
    last_triggered_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "media_counters"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("session_id", ASCENDING), ("automation_id", ASCENDING)],
                unique=True,
            ),
            IndexModel(
                [("updated_at", ASCENDING)],
                expireAfterSeconds=COUNTER_TTL_SECONDS,
            ),
        ]


class AutomationExecution(Document):
    """Audit trail for one automation run."""

    session_id: str
    automation_id: str
    automation_name: str | None = None
    event_id: str
    event_type: str
    status: str = "running"  # running | success | failed | partial
    actions: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    class Settings:
        name = "automation_executions"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("session_id", ASCENDING), ("started_at", DESCENDING)]),
            IndexModel(
                [("started_at", ASCENDING)],
                expireAfterSeconds=EXECUTION_TTL_SECONDS,
            ),
        ]
