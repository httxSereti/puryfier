"""Tests for lock_frozen readiness gating (SDK review 3.1)."""

import asyncio

import models.connection_manager as manager_module
from routes.webhooks.actions import handle_lock_frozen


def run(coro):
    return asyncio.run(coro)


class FakeConnection:
    """A live connection whose readiness and drain outcome are controlled."""

    def __init__(
        self,
        *,
        ready: bool = True,
        intents_granted: bool = True,
        delivered: bool = True,
    ):
        self.ready = ready
        self.intents_granted = intents_granted
        self.delivered = delivered
        self.flush_calls = 0

    async def flush_queue(self) -> bool:
        self.flush_calls += 1
        return self.delivered


def make_payload(session_id: str = "session-1") -> dict:
    return {
        "event": "action_log.created",
        "requestId": "req-1",
        "data": {
            "sessionId": session_id,
            "actionLog": {"type": "lock_frozen"},
        },
    }


def queued_messages(mongo_db, link_token: str) -> list[dict]:
    return list(
        mongo_db["queued_messages"]
        .find({"link_token": link_token})
        .sort("_id", 1)
    )


class TestReadinessGating:
    def test_ready_connection_flushes_and_reports_processed(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(session_id="session-1", link_token="tok-ok")
        fake = FakeConnection(delivered=True)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_frozen(make_payload()))

        assert result["action"] == "lock_frozen_processed"
        assert fake.flush_calls == 1

        # Commands are persisted before any delivery attempt: this is what
        # makes the lock lossless when PuryFi is not ready yet.
        queued = queued_messages(mongo_db, "tok-ok")
        assert [message["msg_type"] for message in queued] == [
            "setState",
            "setState",
        ]

        stored = mongo_db["users_lock_configurations"].find_one(
            {"session_id": "session-1"}
        )
        # SDK review 3.3: send the full WriteOnlyValue<"lockConfiguration">
        # shape, including the explicit null timer fields.
        # SDK review 6.2: configure the lock before enabling PuryFi, so a
        # failed lockConfiguration cannot leave it enabled without a lock.
        assert queued[0]["payload"] == {
            "path": "lockConfiguration",
            "value": {
                "password": {"secret": stored["lock_password"]},
                "timer": None,
                "timerPlus": None,
            },
        }
        assert queued[1]["payload"] == {"path": "enabled", "value": True}

    def test_before_ready_keeps_commands_queued(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-before-ready"
        )
        fake = FakeConnection(ready=False, intents_granted=False, delivered=True)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_frozen(make_payload()))

        assert result == {
            "status": "ok",
            "action": "lock_frozen_queued_not_ready",
        }
        # Readiness is enforced before touching the connection, even if the
        # adapter would claim a successful drain.
        assert fake.flush_calls == 0
        assert len(queued_messages(mongo_db, "tok-before-ready")) == 2

    def test_before_intents_grant_keeps_commands_queued(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-before-intents"
        )
        fake = FakeConnection(
            ready=True, intents_granted=False, delivered=True
        )
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_frozen(make_payload()))

        assert result["action"] == "lock_frozen_queued_not_ready"
        assert fake.flush_calls == 0
        assert len(queued_messages(mongo_db, "tok-before-intents")) == 2

    def test_flush_failure_does_not_report_processed(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(session_id="session-1", link_token="tok-fail")
        fake = FakeConnection(delivered=False)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_frozen(make_payload()))

        assert result["action"] == "lock_frozen_queued_not_ready"
        assert len(queued_messages(mongo_db, "tok-fail")) == 2
