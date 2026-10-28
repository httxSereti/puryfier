"""E2E tests for POST /api/webhooks/extensions/chaster.

Covers webhook authentication, defensive payload parsing (400s), durable inbox
acceptance, and business event deduplication: Chaster gives every retry a new
requestId, so retries must be detected from the action log / session identity.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TEST_DB_NAME, WEBHOOK_AUTH
from fastapi.testclient import TestClient

WEBHOOK_URL = "/api/webhooks/extensions/chaster"
INBOX_TIMEOUT = 3.0


def make_payload(
    request_id: str = "req-1",
    event: str = "action_log.created",
    action_type: str = "some_unhandled_action",
    session_id: str | None = None,
    action_id: str | None = "action-1",
) -> dict:
    data: dict = {"actionLog": {"type": action_type, "_id": action_id}}
    if session_id is not None:
        data["sessionId"] = session_id
    return {"event": event, "requestId": request_id, "data": data}


def make_session_payload(
    request_id: str = "req-session-1",
    event: str = "extension_session.updated",
    session_id: str = "session-1",
    updated_at: str = "2026-10-28T10:00:00Z",
) -> dict:
    return {
        "event": event,
        "requestId": request_id,
        "data": {"session": {"sessionId": session_id, "updatedAt": updated_at}},
    }


def action_key(action_id: str) -> str:
    return f"action_log.created:{action_id}"


def wait_for_inbox(
    mongo_db,
    event_key: str,
    statuses: tuple[str, ...] = ("done", "failed"),
    timeout: float = INBOX_TIMEOUT,
) -> dict:
    """Wait for the background worker to settle an inbox entry."""
    deadline = time.monotonic() + timeout
    last_doc = None
    while time.monotonic() < deadline:
        last_doc = mongo_db["webhook_inbox"].find_one({"event_key": event_key})
        if last_doc is not None and last_doc.get("status") in statuses:
            return last_doc
        time.sleep(0.01)
    raise AssertionError(f"Webhook {event_key!r} not settled; last state: {last_doc}")


class TestAuthentication:
    def test_missing_credentials_returns_401(self, client):
        response = client.post(WEBHOOK_URL, json=make_payload())
        assert response.status_code == 401

    def test_wrong_credentials_returns_401(self, client):
        response = client.post(WEBHOOK_URL, json=make_payload(), auth=("nope", "nope"))
        assert response.status_code == 401

    def test_valid_credentials_accepted(self, client):
        response = client.post(WEBHOOK_URL, json=make_payload(), auth=WEBHOOK_AUTH)
        assert response.status_code == 202
        assert response.json() == {"status": "ok", "action": "accepted"}

    @pytest.mark.parametrize(
        ("user", "password"),
        [
            ("", ""),
            ("   ", "   "),
            ("", "test_webhook_pwd"),
            ("test_webhook_user", ""),
        ],
        ids=["empty", "whitespace", "missing-user", "missing-password"],
    )
    def test_unconfigured_credentials_fail_closed(
        self, client, monkeypatch, user, password
    ):
        """Empty credentials must never authenticate (Basic Og== must be denied)."""
        monkeypatch.setenv("CHASTER_WEBHOOK_USER", user)
        monkeypatch.setenv("CHASTER_WEBHOOK_PWD", password)

        response = client.post(
            WEBHOOK_URL, json=make_payload(), auth=(user, password)
        )

        assert response.status_code == 503

    def test_app_refuses_to_start_without_webhook_credentials(
        self, monkeypatch, mongo
    ):
        import db as db_module

        monkeypatch.setattr(
            db_module, "AsyncMongoClient", lambda *args, **kwargs: mongo
        )
        monkeypatch.setenv("DATABASE_URL", f"mongodb://localhost:27017/{TEST_DB_NAME}")
        monkeypatch.setenv("CHASTER_WEBHOOK_USER", "")
        monkeypatch.setenv("CHASTER_WEBHOOK_PWD", "")

        from main import app

        with pytest.raises(RuntimeError, match="CHASTER_WEBHOOK_USER"), TestClient(app):
            pass


class TestDefensiveParsing:
    def test_invalid_json_returns_400(self, client):
        response = client.post(
            WEBHOOK_URL,
            content="{not json",
            headers={"Content-Type": "application/json"},
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 400

    def test_non_object_json_returns_400(self, client):
        response = client.post(WEBHOOK_URL, json=["event"], auth=WEBHOOK_AUTH)
        assert response.status_code == 400

    def test_missing_event_returns_400(self, client):
        response = client.post(WEBHOOK_URL, json={"requestId": "req-1"}, auth=WEBHOOK_AUTH)
        assert response.status_code == 400

    def test_missing_request_id_returns_400(self, client):
        response = client.post(
            WEBHOOK_URL, json={"event": "action_log.created"}, auth=WEBHOOK_AUTH
        )
        assert response.status_code == 400

    def test_missing_action_log_returns_400(self, client):
        response = client.post(
            WEBHOOK_URL,
            json={"event": "action_log.created", "requestId": "req-1"},
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 400

    def test_null_data_returns_400(self, client):
        response = client.post(
            WEBHOOK_URL,
            json={"event": "action_log.created", "requestId": "req-1", "data": None},
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 400

    def test_missing_action_type_returns_400(self, client):
        response = client.post(
            WEBHOOK_URL,
            json={
                "event": "action_log.created",
                "requestId": "req-1",
                "data": {"actionLog": {}},
            },
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 400

    def test_missing_action_log_id_returns_400(self, client):
        """Without actionLog._id there is no business key to deduplicate on."""
        response = client.post(
            WEBHOOK_URL,
            json={
                "event": "action_log.created",
                "requestId": "req-1",
                "data": {"actionLog": {"type": "lock_frozen"}},
            },
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 400


class TestDurableInbox:
    def test_endpoint_acknowledges_before_slow_handler(
        self, client, mongo_db, monkeypatch
    ):
        """P0: Chaster must get a fast 202, even when the handler takes seconds."""
        import routes.webhooks.actions as actions_module

        async def slow_handler(_payload):
            await asyncio.sleep(0.75)
            return {"status": "ok"}

        monkeypatch.setattr(actions_module, "handle_lock_frozen", slow_handler)

        payload = make_payload(
            action_type="lock_frozen",
            session_id="session-1",
            action_id="action-slow",
        )
        started = time.perf_counter()
        response = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)
        elapsed = time.perf_counter() - started

        assert response.status_code == 202
        assert response.json() == {"status": "ok", "action": "accepted"}
        assert elapsed < 0.5

        entry = wait_for_inbox(mongo_db, action_key("action-slow"))
        assert entry["status"] == "done"

    def test_expired_processing_lease_is_reclaimed(self, client, mongo_db):
        """A crash left an entry processing; its lease must be reclaimable."""
        from workers.webhook_inbox import webhook_worker

        payload = make_payload(action_id="action-stale")
        now = datetime.now(UTC)
        mongo_db["webhook_inbox"].insert_one(
            {
                "event_key": action_key("action-stale"),
                "event": "action_log.created",
                "request_id": "req-stale",
                "payload": payload,
                "status": "processing",
                "attempts": 1,
                "locked_until": now - timedelta(seconds=1),
                "created_at": now - timedelta(seconds=10),
                "updated_at": now,
            }
        )

        webhook_worker.wake()
        entry = wait_for_inbox(mongo_db, action_key("action-stale"))

        assert entry["status"] == "done"
        assert entry["attempts"] == 2

    def test_handler_failure_is_retried_then_succeeds(
        self, client, mongo_db, monkeypatch
    ):
        import routes.webhooks.actions as actions_module
        from workers.webhook_inbox import webhook_worker

        calls = {"count": 0}

        async def flaky_handler(_payload):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient failure")
            return {"status": "ok"}

        monkeypatch.setattr(actions_module, "handle_lock_frozen", flaky_handler)
        monkeypatch.setattr(webhook_worker, "retry_base_seconds", 0)

        payload = make_payload(
            action_type="lock_frozen",
            session_id="session-1",
            action_id="action-flaky",
        )
        response = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)
        assert response.status_code == 202

        entry = wait_for_inbox(mongo_db, action_key("action-flaky"))
        assert entry["status"] == "done"
        assert entry["attempts"] == 2
        assert calls["count"] == 2

    def test_exhausted_retries_marks_entry_failed(
        self, client, mongo_db, monkeypatch
    ):
        import routes.webhooks.actions as actions_module
        from workers.webhook_inbox import webhook_worker

        async def broken_handler(_payload):
            raise RuntimeError("permanent failure")

        monkeypatch.setattr(actions_module, "handle_lock_frozen", broken_handler)
        monkeypatch.setattr(webhook_worker, "max_attempts", 2)
        monkeypatch.setattr(webhook_worker, "retry_base_seconds", 0)

        payload = make_payload(
            action_type="lock_frozen",
            session_id="session-1",
            action_id="action-broken",
        )
        response = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)
        assert response.status_code == 202

        entry = wait_for_inbox(mongo_db, action_key("action-broken"))
        assert entry["status"] == "failed"
        assert entry["attempts"] == 2
        assert "RuntimeError" in entry["last_error"]


class TestSessionDeleted:
    def test_deleted_session_without_updated_at_is_purged(
        self, client, mongo_db, seed_lock_configuration
    ):
        """Deletion is terminal and may not carry updatedAt: the session id is
        still a stable idempotency key."""
        seed_lock_configuration(session_id="session-del", link_token="token-del")
        mongo_db["queued_messages"].insert_one(
            {
                "link_token": "token-del",
                "msg_type": "setState",
                "payload": {"path": "enabled", "value": False},
                "created_at": "2026-01-01T00:00:00Z",
            }
        )
        payload = {
            "event": "extension_session.deleted",
            "requestId": "req-del-1",
            "data": {"session": {"sessionId": "session-del"}},
        }

        response = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)

        assert response.status_code == 202
        entry = wait_for_inbox(
            mongo_db, "extension_session.deleted:session-del"
        )
        assert entry["status"] == "done"
        assert (
            mongo_db["users_lock_configurations"].find_one(
                {"session_id": "session-del"}
            )
            is None
        )
        assert (
            mongo_db["queued_messages"].count_documents({"link_token": "token-del"})
            == 0
        )

        retry = {
            "event": "extension_session.deleted",
            "requestId": "req-del-2",
            "data": {"session": {"sessionId": "session-del"}},
        }
        duplicate = client.post(WEBHOOK_URL, json=retry, auth=WEBHOOK_AUTH)

        assert duplicate.status_code == 200
        assert duplicate.json() == {
            "status": "ok",
            "action": "duplicate_ignored",
        }

    def test_deleted_session_uses_updated_at_when_present(self, client, mongo_db):
        payload = {
            "event": "extension_session.deleted",
            "requestId": "req-del-updated",
            "data": {
                "session": {
                    "sessionId": "session-del-2",
                    "updatedAt": "2026-10-28T12:00:00Z",
                }
            },
        }

        response = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)

        assert response.status_code == 202
        entry = wait_for_inbox(
            mongo_db,
            "extension_session.deleted:session-del-2:2026-10-28T12:00:00Z",
        )
        assert entry["status"] == "done"


class TestDeduplication:
    def test_retry_with_new_request_id_is_noop(self, client, mongo_db):
        """Chaster changes requestId on every retry; actionLog._id is stable."""
        first_payload = make_payload(request_id="req-dup-1", action_id="action-dup-1")
        retry_payload = make_payload(request_id="req-dup-2", action_id="action-dup-1")

        first = client.post(WEBHOOK_URL, json=first_payload, auth=WEBHOOK_AUTH)
        assert first.status_code == 202
        assert first.json()["action"] == "accepted"
        wait_for_inbox(mongo_db, action_key("action-dup-1"))

        retry = client.post(WEBHOOK_URL, json=retry_payload, auth=WEBHOOK_AUTH)
        assert retry.status_code == 200
        assert retry.json() == {"status": "ok", "action": "duplicate_ignored"}
        assert (
            mongo_db["webhook_inbox"].count_documents(
                {"event_key": action_key("action-dup-1")}
            )
            == 1
        )

    def test_different_action_log_ids_are_both_processed(self, client, mongo_db):
        first = make_payload(request_id="req-a-1", action_id="action-a")
        second = make_payload(request_id="req-a-2", action_id="action-b")

        assert client.post(WEBHOOK_URL, json=first, auth=WEBHOOK_AUTH).status_code == 202
        assert client.post(WEBHOOK_URL, json=second, auth=WEBHOOK_AUTH).status_code == 202
        wait_for_inbox(mongo_db, action_key("action-a"))
        wait_for_inbox(mongo_db, action_key("action-b"))
        assert mongo_db["webhook_inbox"].count_documents({}) == 2

    def test_extension_session_retry_uses_session_identity(self, client, mongo_db):
        key = "extension_session.updated:session-1:2026-10-28T10:00:00Z"
        first = make_session_payload(request_id="req-session-1")
        retry = make_session_payload(request_id="req-session-2")

        assert client.post(WEBHOOK_URL, json=first, auth=WEBHOOK_AUTH).status_code == 202
        wait_for_inbox(mongo_db, key)
        response = client.post(WEBHOOK_URL, json=retry, auth=WEBHOOK_AUTH)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "action": "duplicate_ignored"}
        assert mongo_db["webhook_inbox"].count_documents({"event_key": key}) == 1

    def test_extension_session_new_updated_at_is_a_new_event(self, client, mongo_db):
        first = make_session_payload(
            request_id="req-session-1", updated_at="2026-10-28T10:00:00Z"
        )
        update = make_session_payload(
            request_id="req-session-2", updated_at="2026-10-28T10:05:00Z"
        )

        assert client.post(WEBHOOK_URL, json=first, auth=WEBHOOK_AUTH).status_code == 202
        assert client.post(WEBHOOK_URL, json=update, auth=WEBHOOK_AUTH).status_code == 202
        wait_for_inbox(
            mongo_db, "extension_session.updated:session-1:2026-10-28T10:00:00Z"
        )
        wait_for_inbox(
            mongo_db, "extension_session.updated:session-1:2026-10-28T10:05:00Z"
        )
        assert mongo_db["webhook_inbox"].count_documents({}) == 2

    def test_retried_lock_frozen_does_not_regenerate_password_or_requeue(
        self, client, mongo_db, seed_lock_configuration
    ):
        """Regression test: a retried lock_frozen used to generate a new
        password and re-queue the setState messages."""
        seed_lock_configuration(session_id="session-1", link_token="token-1")
        payload = make_payload(
            request_id="req-freeze-1",
            action_type="lock_frozen",
            session_id="session-1",
            action_id="action-freeze-1",
        )
        retry_payload = make_payload(
            request_id="req-freeze-2",
            action_type="lock_frozen",
            session_id="session-1",
            action_id="action-freeze-1",
        )

        first = client.post(WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH)
        assert first.status_code == 202
        wait_for_inbox(mongo_db, action_key("action-freeze-1"))

        config = mongo_db["users_lock_configurations"].find_one(
            {"session_id": "session-1"}
        )
        assert config["lock_password"]  # generated by the handler
        assert mongo_db["queued_messages"].count_documents({"link_token": "token-1"}) == 2

        retry = client.post(WEBHOOK_URL, json=retry_payload, auth=WEBHOOK_AUTH)
        assert retry.status_code == 200
        assert retry.json()["action"] == "duplicate_ignored"

        config_after = mongo_db["users_lock_configurations"].find_one(
            {"session_id": "session-1"}
        )
        assert config_after["lock_password"] == config["lock_password"]
        assert mongo_db["queued_messages"].count_documents({"link_token": "token-1"}) == 2
