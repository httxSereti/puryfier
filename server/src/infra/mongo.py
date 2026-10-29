import os

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.uri_parser import parse_uri

from infra.documents import QueuedMessage, UserLockConfiguration, WebhookInboxEntry
from infra.logging import get_logger

log = get_logger(__name__)

_client: AsyncMongoClient | None = None

DEFAULT_DB_NAME = "puryfi_chaster"


def _resolve_db_name(url: str) -> str:
    """Database name: explicit env var wins, otherwise parse the URI properly
    (REVIEW.md #19 — no string hacking on the connection string)."""
    explicit = os.getenv("DATABASE_NAME", "")
    if explicit:
        return explicit
    return parse_uri(url)["database"] or DEFAULT_DB_NAME


async def init_db() -> None:
    """Initialise the MongoDB connection and register all Beanie documents."""
    global _client

    url = os.getenv(
        "DATABASE_URL",
        f"mongodb://puryfi:puryfi@localhost:27017/{DEFAULT_DB_NAME}?authSource=admin",
    )

    _client = AsyncMongoClient(url)

    db_name = _resolve_db_name(url)
    log.info("db.connecting", database=db_name)

    await init_beanie(
        database=_client[db_name],
        document_models=[UserLockConfiguration, QueuedMessage, WebhookInboxEntry],
    )
    log.info("db.ready", database=db_name)


async def close_db() -> None:
    """Cleanly close the MongoDB client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
        log.info("db.closed")
