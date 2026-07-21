"""Shared fixtures for e2e API tests.

Each test gets:
- `client`    -- httpx TestClient driving the real FastAPI app (routing, auth,
                 validation, beanie documents) over HTTP, backed by a fresh
                 in-memory Mongo. No Docker / MongoDB server required.
- `mongo_db`  -- synchronous handle to the same in-memory store, for seeding
                 data and asserting on what the app wrote.
- `seed_lock_configuration` -- factory for UserLockConfiguration documents.

Add per-endpoint test modules next to this file (test_extensions.py,
test_configuration.py, test_websocket.py, ...) and reuse these fixtures.
"""

import pytest
from fastapi.testclient import TestClient

from memory_mongo import InMemoryMongoClient

TEST_DB_NAME = "puryfi_chaster_test"
TEST_WEBHOOK_USER = "test_webhook_user"
TEST_WEBHOOK_PWD = "test_webhook_pwd"
WEBHOOK_AUTH = (TEST_WEBHOOK_USER, TEST_WEBHOOK_PWD)


@pytest.fixture()
def mongo() -> InMemoryMongoClient:
    """A fresh, empty in-memory Mongo per test."""
    return InMemoryMongoClient()


@pytest.fixture()
def client(mongo: InMemoryMongoClient, monkeypatch: pytest.MonkeyPatch):
    """TestClient on the real app, with Mongo swapped for the in-memory one.

    Env vars are set before the app is imported so `load_dotenv()` cannot
    override them with real values from .env (it does not override existing
    variables). A fresh `mongo` per test gives full database isolation.
    """
    import db as db_module

    monkeypatch.setattr(db_module, "AsyncMongoClient", lambda *args, **kwargs: mongo)
    monkeypatch.setenv("DATABASE_URL", f"mongodb://localhost:27017/{TEST_DB_NAME}")
    monkeypatch.setenv("CHASTER_WEBHOOK_USER", TEST_WEBHOOK_USER)
    monkeypatch.setenv("CHASTER_WEBHOOK_PWD", TEST_WEBHOOK_PWD)

    from main import app

    # raise_server_exceptions=False: server errors surface as 500 responses
    # so tests can assert on them instead of raising.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def mongo_db(mongo: InMemoryMongoClient):
    """Sync handle to the test database for seeding/assertions."""
    return mongo.sync_client[TEST_DB_NAME]


@pytest.fixture()
def seed_lock_configuration(mongo_db):
    """Insert a UserLockConfiguration document; returns the inserted doc."""

    def _seed(
        session_id: str = "session-1",
        link_token: str = "token-1",
        lock_on_freeze: bool = True,
        unlock_on_unfreeze: bool = True,
        **overrides,
    ) -> dict:
        doc = {
            "lock_id": None,
            "session_id": session_id,
            "link_token": link_token,
            "has_linked_plugin": True,
            "keyholder_id": None,
            "wearer_id": None,
            "puryfi_username": None,
            "lock_password": None,
            "config": {
                "lock_on_freeze": lock_on_freeze,
                "unlock_on_unfreeze": unlock_on_unfreeze,
                "censorPicsConfig": {
                    "limit_count": 100,
                    "added_duration": 600,
                    "enabled": False,
                },
            },
        }
        doc.update(overrides)
        mongo_db["users_lock_configurations"].insert_one(doc)
        return doc

    return _seed
