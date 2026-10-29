"""Tests for extension_session.deleted cleanup (REVIEW.md critical #12)."""

import asyncio
from types import SimpleNamespace

import pytest

from models.connection_manager import manager
from models.session_watchers import watchers
from services.session_lifecycle import SESSION_ENDED_CLOSE_CODE, revoke_session


@pytest.fixture(autouse=True)
def clean_runtime_state():
    manager._connections.clear()
    manager._locks.clear()
    watchers._watchers.clear()
    yield
    manager._connections.clear()
    manager._locks.clear()
    watchers._watchers.clear()


class FakeConnection:
    def __init__(self, lock_config):
        self.user_lock_config = lock_config
        self.close_codes: list[int] = []

    async def close(self, code: int = 1000) -> None:
        self.close_codes.append(code)


class FakeWatcher:
    def __init__(self):
        self.messages: list[dict] = []
        self.close_codes: list[int] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)

    async def close(self, code: int = 1000) -> None:
        self.close_codes.append(code)


def seed_queue(mongo_db, link_token: str, count: int = 2) -> None:
    mongo_db["queued_messages"].insert_many(
        [
            {
                "link_token": link_token,
                "msg_type": "setState",
                "payload": {"path": "enabled", "value": False},
                "created_at": f"2026-01-01T00:00:0{index}Z",
            }
            for index in range(count)
        ]
    )


class TestRevokeSession:
    def test_purges_configuration_queue_and_revokes_sockets(
        self, client, mongo_db, seed_lock_configuration
    ):
        seed_lock_configuration(
            session_id="session-1",
            link_token="token-1",
            has_linked_plugin=True,
        )
        seed_queue(mongo_db, "token-1")

        lock_config = SimpleNamespace(
            session_id="session-1",
            link_token="token-1",
            has_linked_plugin=True,
        )
        connection = FakeConnection(lock_config)
        manager._connections["token-1"] = connection
        watcher = FakeWatcher()
        watchers._watchers["session-1"] = {watcher}

        deleted = asyncio.run(revoke_session("session-1"))

        assert deleted is True
        assert connection.close_codes == [SESSION_ENDED_CLOSE_CODE]
        assert watcher.close_codes == [SESSION_ENDED_CLOSE_CODE]
        # Watchers were told the plugin went offline before they were closed.
        assert watcher.messages == [
            {"type": "status", "is_online": False, "has_linked_plugin": True}
        ]
        assert (
            mongo_db["users_lock_configurations"].find_one(
                {"session_id": "session-1"}
            )
            is None
        )
        assert mongo_db["queued_messages"].count_documents({"link_token": "token-1"}) == 0

    def test_missing_configuration_still_closes_watchers(self, client, mongo_db):
        watcher = FakeWatcher()
        watchers._watchers["missing-session"] = {watcher}

        deleted = asyncio.run(revoke_session("missing-session"))

        assert deleted is False
        assert watcher.close_codes == [SESSION_ENDED_CLOSE_CODE]
        assert mongo_db["users_lock_configurations"].count_documents({}) == 0
