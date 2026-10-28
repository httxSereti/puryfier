from datetime import UTC, datetime
from typing import Annotated, ClassVar

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# How long a processed request id is remembered for deduplication.
# Comfortably covers Chaster's webhook retry window.
DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


class ProcessedWebhookEvent(Document):
    """Request id of an already-processed Chaster webhook, used to make retries no-ops."""

    request_id: Annotated[str, Indexed(unique=True)]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "processed_webhook_events"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=DEDUP_TTL_SECONDS),
        ]
