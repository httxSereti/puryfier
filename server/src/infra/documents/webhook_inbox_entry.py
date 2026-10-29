from datetime import UTC, datetime
from typing import Any, ClassVar

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# Durable inbox entries are delivery state, not history. Chaster retries happen
# within minutes, but a week gives us plenty of room to diagnose a failure.
INBOX_TTL_SECONDS = 7 * 24 * 60 * 60


class WebhookInboxEntry(Document):
    """Durable inbox for Chaster webhooks.

    The webhook endpoint only validates and stores the event; a background
    worker processes it. `event_key` is the idempotency key and is derived from
    the business event (action log id, session id, ...), never from the
    requestId: Chaster changes the requestId on every retry.
    """

    event_key: str
    event: str
    request_id: str | None = None
    payload: dict[str, Any]

    # pending | processing | done | failed
    status: str = "pending"
    attempts: int = 0
    available_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    locked_until: datetime | None = None
    last_error: str | None = None
    processed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "webhook_inbox"
        indexes: ClassVar[list[IndexModel]] = [
            # Partial index so old documents without the field, or future
            # optional keys, do not conflict with each other.
            IndexModel(
                [("event_key", ASCENDING)],
                unique=True,
                partialFilterExpression={"event_key": {"$type": "string"}},
            ),
            IndexModel([("status", ASCENDING), ("available_at", ASCENDING)]),
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=INBOX_TTL_SECONDS,
            ),
        ]
