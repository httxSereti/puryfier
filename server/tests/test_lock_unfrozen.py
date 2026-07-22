"""Tests for lock_unfrozen handler robustness (REVIEW.md #20)."""

import asyncio

import models.connection_manager as manager_module
from routes.webhooks.actions import handle_lock_unfrozen


def run(coro):
    return asyncio.run(coro)


class FakeConnection:
    """Records messages sent to the Puryfi client."""

    def __init__(self, responses: list[dict]):
        self.sent: list[tuple[str, dict]] = []
        self._responses = responses

    async def send_message(self, msg_type: str, payload: dict) -> dict:
        self.sent.append((msg_type, payload))
        return self._responses.pop(0)


def make_payload(session_id: str = "session-1") -> dict:
    return {
        "event": "action_log.created",
        "requestId": "req-1",
        "data": {
            "sessionId": session_id,
            "actionLog": {"type": "lock_unfrozen"},
        },
    }


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
    def test_error_response_without_type_key_is_handled(
        self, client, seed_lock_configuration, monkeypatch
    ):
        """A plugin error payload lacking 'type' must not raise KeyError."""
        seed_lock_configuration(
            session_id="session-1", link_token="tok-err", lock_password="s3cret"
        )
        # Plugin answers with a payload that has neither 'type' nor 'error'.
        fake = FakeConnection(responses=[{"unexpected": True}])
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["status"] == "error"
        assert result["error"] == "unknown_error"

    def test_happy_path_unlocks_and_disables(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-ok", lock_password="s3cret"
        )
        fake = FakeConnection(responses=[{"type": "ok"}, {"type": "ok"}])
        monkeypatch.setattr(
            manager_module.manager, "get_by_user_link_token", lambda _t: fake
        )

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["action"] == "lock_unfrozen_processed"
        assert fake.sent == [
            ("enterLockPassword", {"secret": "s3cret"}),
            ("setState", {"path": "enabled", "value": False}),
        ]

    def test_no_connection_queues_with_real_password(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="session-1", link_token="tok-q", lock_password="s3cret"
        )
        # No live connection registered for tok-q.

        result = run(handle_lock_unfrozen(make_payload()))

        assert result["action"] == "lock_unfrozen_queued_no_connection"
        queued = list(mongo_db["queued_messages"].find({"link_token": "tok-q"}))
        assert len(queued) == 2
        assert queued[0]["payload"] == {"secret": "s3cret"}
