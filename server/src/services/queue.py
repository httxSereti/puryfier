from models.documents.queued_message import QueuedMessage
from utils.logging_config import get_logger
from utils.redaction import token_fingerprint

log = get_logger(__name__)

# Per-token cap so the queue cannot grow unboundedly for users who never
# reconnect (REVIEW.md #9). The TTL index on QueuedMessage handles expiry.
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


async def fetch_queued_messages(link_token: str) -> list[QueuedMessage]:
    """Return queued messages in insertion order, WITHOUT deleting them.

    Callers delete each message only after it was delivered successfully, so a
    crash mid-drain cannot lose messages (REVIEW.md #9).
    """
    return await QueuedMessage.find(
        QueuedMessage.link_token == link_token
    ).sort("+created_at").to_list()
