from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.uri_parser import parse_uri

from config import Settings, get_settings
from infra.documents import QueuedMessage, UserLockConfiguration, WebhookInboxEntry
from infra.logging import get_logger

log = get_logger(__name__)

_client: AsyncMongoClient | None = None

DEFAULT_DB_NAME = "puryfi_chaster"


def _resolve_db_name(url: str, explicit: str | None) -> str:
    """Database name: explicit setting wins, otherwise parse the URI properly
    (REVIEW.md #19 — no string hacking on the connection string)."""
    if explicit:
        return explicit
    return parse_uri(url)["database"] or DEFAULT_DB_NAME


async def init_db(settings: Settings | None = None) -> None:
    """Initialise the MongoDB connection and register all Beanie documents."""
    global _client

    settings = settings or get_settings()
    _client = AsyncMongoClient(settings.database_url)

    db_name = _resolve_db_name(settings.database_url, settings.database_name)
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
