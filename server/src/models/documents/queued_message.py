from datetime import datetime, timezone
from typing import Any, Annotated

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# Queued messages are delivery state, not history: expire them (REVIEW.md #9).
QUEUE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


class QueuedMessage(Document):
    """A message queued for delivery when a Puryfi connection comes online."""

    link_token: Annotated[str, Indexed()]
    msg_type: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "queued_messages"
        indexes = [
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=QUEUE_TTL_SECONDS),
        ]
