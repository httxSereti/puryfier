"""Tests for lock_unfrozen handler robustness (REVIEW.md #20)."""

import asyncio

import models.connection_manager as manager_module
from routes.webhooks.actions import handle_lock_unfrozen


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
            "actionLog": {"type": "lock_unfrozen"},
        },
    }


def queued_messages(mongo_db, link_token: str) -> list[dict]:
    return list(
        mongo_db["queued_messages"]
        .find({"link_token": link_token})
        .sort("_id", 1)
    )


class TestMissingKeys:
    def test_missing_session_id_is_ignored_not_500(self, client):
        payload = {"event": "action_log.created", "requestId": "r", "data": {}}
        result = run(handle_lock_unfrozen(payload))
        assert result["action"] == "lock_unfrozen_ignored_no_session"


class TestNoPassword:
    def test_no_password_never_sends_none_secret(
        self, client, seed_lock_configuration
    ):
        """queued enterLockPassword must never carry {"secret": None}."""
        seed_lock_configuration(
            session_id="session-1", link_token="tok-np", lock_password=None
        )

        result = run(handle_lock_unfrozen(make_payload()))

        assert result == {"status": "error", "error": "no_lock_password"}


class TestPluginResponses:
    def test_ready_connection_flushes_and_reports_processed(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-ok", lock_password="s3cret"
        )
        fake = FakeConnection(delivered=True)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["action"] == "lock_unfrozen_processed"
        assert fake.flush_calls == 1

        # Commands are persisted before any delivery attempt: this is what
        # makes the unlock lossless when PuryFi is not ready yet.
        queued = queued_messages(mongo_db, "tok-ok")
        assert [message["msg_type"] for message in queued] == [
            "enterLockPassword",
            "setState",
        ]
        assert queued[0]["payload"] == {"secret": "s3cret"}
        assert queued[1]["payload"] == {"path": "enabled", "value": False}

    def test_not_ready_connection_keeps_commands_queued(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-pending", lock_password="s3cret"
        )
        fake = FakeConnection(ready=False, intents_granted=False, delivered=False)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_unfrozen(make_payload()))

        # Never claim success when PuryFi did not apply the commands.
        assert result == {
            "status": "ok",
            "action": "lock_unfrozen_queued_not_ready",
        }
        assert fake.flush_calls == 1
        assert len(queued_messages(mongo_db, "tok-pending")) == 2

    def test_flush_failure_does_not_report_processed(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-fail", lock_password="s3cret"
        )
        fake = FakeConnection(delivered=False)
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["action"] == "lock_unfrozen_queued_not_ready"
        assert len(queued_messages(mongo_db, "tok-fail")) == 2

    def test_no_connection_queues_with_real_password(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-q", lock_password="s3cret"
        )
        # No live connection registered for tok-q.

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["action"] == "lock_unfrozen_queued_no_connection"
        queued = queued_messages(mongo_db, "tok-q")
        assert len(queued) == 2
        assert queued[0]["payload"] == {"secret": "s3cret"}
