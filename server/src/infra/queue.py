"""Durable outbound message queue.

Queued messages are delivery state, not history: they are capped per token and
expire through a MongoDB TTL index.
"""

from typing import Any

from bson import ObjectId

from domain.entities import QueuedCommand
from infra.documents.queued_message import QueuedMessage
from infra.logging import get_logger
from infra.redaction import token_fingerprint

log = get_logger(__name__)

# Per-token cap so the queue cannot grow unboundedly for users who never
# reconnect. The TTL index on QueuedMessage handles expiry.
MAX_QUEUED_PER_TOKEN = 100


async def queue_message(link_token: str, msg_type: str, payload: dict) -> None:
    count = await QueuedMessage.find(
        QueuedMessage.link_token == link_token
    ).count()

    if count >= MAX_QUEUED_PER_TOKEN:
        # Drop the oldest message to make room: for a state-sync protocol the
        # newest state matters more than the oldest pending one.
        oldest = await QueuedMessage.find(
            QueuedMessage.link_token == link_token
        ).sort("+created_at").first_or_none()
        if oldest is not None:
            await oldest.delete()
        log.warning(
            "queue.cap_reached",
            link_token=token_fingerprint(link_token),
            cap=MAX_QUEUED_PER_TOKEN,
            dropped_message_type=oldest.msg_type if oldest is not None else None,
        )

    msg = QueuedMessage(link_token=link_token, msg_type=msg_type, payload=payload)
    await msg.insert()


async def fetch_queued_messages(link_token: str) -> list[QueuedCommand]:
    """Return queued messages in insertion order, WITHOUT deleting them.

    Callers delete each message only after it was delivered successfully, so a
    crash mid-drain cannot lose messages.
    """
    documents = await QueuedMessage.find(
        QueuedMessage.link_token == link_token
    ).sort("+created_at").to_list()
    return [
        QueuedCommand(
            id=str(document.id),
            link_token=document.link_token,
            msg_type=document.msg_type,
            payload=document.payload,
        )
        for document in documents
    ]


class MongoMessageQueue:
    """Beanie-backed implementation of the domain ``MessageQueue`` port."""

    async def enqueue(
        self, link_token: str, msg_type: str, payload: dict[str, Any]
    ) -> None:
        await queue_message(link_token, msg_type, payload)

    async def fetch(self, link_token: str) -> list[QueuedCommand]:
        return await fetch_queued_messages(link_token)

    async def delete(self, command: QueuedCommand) -> None:
        object_id = ObjectId(command.id)
        await QueuedMessage.get_pymongo_collection().delete_one({"_id": object_id})

    async def delete_for_token(self, link_token: str) -> None:
        await QueuedMessage.find(QueuedMessage.link_token == link_token).delete()
