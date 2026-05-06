import os
from beanie import init_beanie
from pymongo import AsyncMongoClient
from models.documents import User, UserLockConfiguration, QueuedMessage


_client: AsyncMongoClient | None = None


async def init_db() -> None:
    """Initialise the MongoDB connection and register all Beanie documents."""
    global _client

    url = os.getenv(
        "DATABASE_URL",
        "mongodb://puryfi:puryfi@localhost:27017/puryfi_chaster?authSource=admin",
    )

    _client = AsyncMongoClient(url)

    # Extract the database name from the connection string
    db_name = url.rsplit("/", 1)[-1].split("?")[0] or "puryfi_chaster"
    print(f"[DB] Connecting to MongoDB: {db_name}")

    await init_beanie(
        database=_client[db_name],
        document_models=[User, UserLockConfiguration, QueuedMessage],
    )
    print("[DB] Beanie initialised ✓")


async def close_db() -> None:
    """Cleanly close the MongoDB client."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        print("[DB] MongoDB connection closed")
