"""E2E tests for the Puryfi WebSocket endpoint (REVIEW.md #6, #9).

Drives the real endpoint with a fake Puryfi client speaking msgpack through
the FastAPI TestClient, against the in-memory Mongo.
"""

import time

import msgpack
import pytest
from conftest import WEBHOOK_AUTH
from starlette.websockets import WebSocketDisconnect
from test_extensions import make_chaster_response
from test_webhooks_chaster import wait_for_inbox

from models.connection_manager import manager
from models.session_watchers import watchers
from utils import chaster_api

WEBHOOK_URL = "/api/webhooks/extensions/chaster"

INTENTS = [
    "readUserState",
    "writeLockConfigurationState",
    "writeEnabledState",
    "readMediaProcesses",
]

READY_PAYLOAD = {
    "version": "0.8.7.1",
    "apiVersion": "1.0.0",
    "instanceId": "test-instance",
}


@pytest.fixture(autouse=True)
def clean_manager():
    """The ConnectionManager and watchers are process-wide singletons: isolate tests."""
    manager._connections.clear()
    manager._locks.clear()
    watchers._watchers.clear()
    yield
    manager._connections.clear()
    manager._locks.clear()
    watchers._watchers.clear()


def rpc_response(request_msg: dict, payload: dict) -> bytes:
    return msgpack.packb({"responseId": request_msg["responseId"], "payload": payload})


def send_ready(puryfi, payload: dict | None = None) -> None:
    puryfi.send_bytes(
        msgpack.packb(
            {
                "type": "ready",
                "payload": payload or READY_PAYLOAD,
                "responseId": 999,
            }
        )
    )


def answer_handshake(puryfi) -> None:
    """Answer the server's init RPCs so the plugin becomes fully ready."""
    for _ in range(50):
        message = msgpack.unpackb(puryfi.receive_bytes())
        if "type" not in message:
            continue  # response to the `ready` message itself

        msg_type = message["type"]
        if msg_type == "getPluginIntents":
            puryfi.send_bytes(
                rpc_response(message, {"type": "ok", "intents": INTENTS})
            )
        elif msg_type == "getState":
            puryfi.send_bytes(
                rpc_response(message, {"type": "ok", "value": "test-user"})
            )
        else:
            puryfi.send_bytes(rpc_response(message, {"type": "ok"}))

        if msg_type == "subscribeToStaticMediaScans":
            return

    raise AssertionError("Puryfi handshake did not complete")


class TestLifecycle:
    def test_unknown_token_is_rejected(self, client):
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/no-such-token"),
        ):
            pass
        assert exc_info.value.code == 4004

    def test_connection_registered_then_removed_on_disconnect(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(link_token="ws-tok-1", session_id="ws-session-1")

        with client.websocket_connect("/ws/ws-tok-1") as ws:
            assert manager.get_by_user_link_token("ws-tok-1") is not None
            ws.close()
            for _ in range(100):
                if manager.get_by_user_link_token("ws-tok-1") is None:
                    break
                time.sleep(0.01)

        assert manager.get_by_user_link_token("ws-tok-1") is None

    def test_new_connection_replaces_and_closes_the_old_socket(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(
            session_id="replace-session", link_token="replace-token"
        )

        with client.websocket_connect("/ws/replace-token") as first:
            first_connection = manager.get_by_user_link_token("replace-token")
            assert first_connection is not None

            with client.websocket_connect("/ws/replace-token"):
                for _ in range(100):
                    if (
                        manager.get_by_user_link_token("replace-token")
                        is not first_connection
                    ):
                        break
                    time.sleep(0.01)

                assert (
                    manager.get_by_user_link_token("replace-token")
                    is not first_connection
                )
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    first.receive_bytes()
                assert exc_info.value.code == 4001

        assert manager.get_by_user_link_token("replace-token") is None

    def test_incompatible_api_version_is_refused(
        self, client, seed_lock_configuration
    ):
        """SDK review 3.4: validate `ready.apiVersion` and answer with `name`."""
        seed_lock_configuration(
            link_token="ws-api-v1", session_id="ws-api-session"
        )

        with client.websocket_connect("/ws/ws-api-v1") as puryfi:
            send_ready(
                puryfi,
                {
                    "version": "0.9.0",
                    "apiVersion": "2.0.0",
                    "instanceId": "other-instance",
                },
            )

            response = msgpack.unpackb(puryfi.receive_bytes())
            assert response["responseId"] == 999
            assert response["payload"]["type"] == "error"
            assert response["payload"]["name"] == "incompatibleApiVersion"
            assert "[1.0.0, 2.0.0)" in response["payload"]["message"]

            connection = manager.get_by_user_link_token("ws-api-v1")
            assert connection is not None
            assert connection.ready is False
            assert connection.api_version == "2.0.0"
            assert connection.instance_id == "other-instance"

    def test_malformed_frame_removes_connection(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(link_token="ws-tok-2", session_id="ws-session-2")

        with client.websocket_connect("/ws/ws-tok-2") as ws:
            assert manager.get_by_user_link_token("ws-tok-2") is not None
            ws.send_bytes(b"\xc1")  # 0xc1 is never valid msgpack
            with pytest.raises(WebSocketDisconnect):
                while True:
                    ws.receive_bytes()

        assert manager.get_by_user_link_token("ws-tok-2") is None


class TestQueueDrain:
    def test_drain_is_ordered_and_deletes_after_send(
        self, client, seed_lock_configuration, mongo_db
    ):
        """REVIEW.md #9: queued messages must be delivered in order, and each
        deleted only after successful delivery."""
        seed_lock_configuration(link_token="ws-tok-3", session_id="ws-session-3")
        mongo_db["queued_messages"].insert_many([
            {
                "link_token": "ws-tok-3",
                "msg_type": "enterLockPassword",
                "payload": {"secret": "s3cret"},
                "created_at": "2026-01-01T00:00:01Z",
            },
            {
                "link_token": "ws-tok-3",
                "msg_type": "setState",
                "payload": {"path": "enabled", "value": False},
                "created_at": "2026-01-01T00:00:02Z",
            },
        ])

        received_types: list[str] = []

        with client.websocket_connect("/ws/ws-tok-3") as ws:
            send_ready(ws)

            for _ in range(50):  # bounded pump: never hang the test
                raw = ws.receive_bytes()
                msg = msgpack.unpackb(raw)

                if "type" not in msg:
                    continue  # a response to one of our messages

                msg_type = msg["type"]
                received_types.append(msg_type)

                if msg_type == "getPluginIntents":
                    ws.send_bytes(rpc_response(msg, {"type": "ok", "intents": INTENTS}))
                elif msg_type == "getState":
                    ws.send_bytes(rpc_response(msg, {"type": "ok", "value": "test-user"}))
                else:
                    ws.send_bytes(rpc_response(msg, {"type": "ok"}))

                if "setState" in received_types and "enterLockPassword" in received_types:
                    break

        # Ordering is semantic for a lock/unlock protocol.
        assert received_types.index("enterLockPassword") < received_types.index("setState")

        # Each message is deleted only after a successful send: both were
        # delivered, so the queue must be empty (poll: deletion happens after
        # our response is processed server-side).
        for _ in range(100):
            if mongo_db["queued_messages"].count_documents({"link_token": "ws-tok-3"}) == 0:
                break
            time.sleep(0.01)
        assert mongo_db["queued_messages"].count_documents({"link_token": "ws-tok-3"}) == 0

    def test_failed_send_keeps_message_queued(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(link_token="ws-tok-4", session_id="ws-session-4")
        mongo_db["queued_messages"].insert_one({
            "link_token": "ws-tok-4",
            "msg_type": "setState",
            "payload": {"path": "enabled", "value": True},
            "created_at": "2026-01-01T00:00:01Z",
        })

        with client.websocket_connect("/ws/ws-tok-4") as ws:
            send_ready(ws)

            for _ in range(50):
                msg = msgpack.unpackb(ws.receive_bytes())
                if "type" not in msg:
                    continue

                if msg["type"] == "getPluginIntents":
                    ws.send_bytes(rpc_response(msg, {"type": "ok", "intents": INTENTS}))
                elif msg["type"] == "getState":
                    ws.send_bytes(rpc_response(msg, {"type": "ok", "value": "test-user"}))
                elif msg["type"] == "setState":
                    # Simulate a plugin-side failure that is NOT intents-related.
                    ws.send_bytes(rpc_response(
                        msg, {"type": "error", "name": "invalidPath", "message": "nope"}
                    ))
                    break
                else:
                    ws.send_bytes(rpc_response(msg, {"type": "ok"}))

        for _ in range(100):
            count = mongo_db["queued_messages"].count_documents({"link_token": "ws-tok-4"})
            if count == 1:
                break
            time.sleep(0.01)
        # Not delivered => must still be queued for the next reconnect.
        assert mongo_db["queued_messages"].count_documents({"link_token": "ws-tok-4"}) == 1


class TestLockReadiness:
    def test_lock_frozen_before_ready_is_queued_then_delivered(
        self, client, seed_lock_configuration, mongo_db
    ):
        """SDK review 3.1: a lock webhook racing the handshake must not be lost."""
        seed_lock_configuration(
            link_token="ws-tok-ready", session_id="ws-session-ready"
        )

        with client.websocket_connect("/ws/ws-tok-ready") as puryfi:
            # The socket is registered, but the plugin has not sent `ready`.
            response = client.post(
                WEBHOOK_URL,
                json={
                    "event": "action_log.created",
                    "requestId": "req-lock-ready",
                    "data": {
                        "sessionId": "ws-session-ready",
                        "actionLog": {
                            "type": "lock_frozen",
                            "_id": "action-lock-ready",
                        },
                    },
                },
                auth=WEBHOOK_AUTH,
            )
            assert response.status_code == 202

            entry = wait_for_inbox(
                mongo_db, "action_log.created:action-lock-ready"
            )
            assert entry["status"] == "done"
            # Nothing was sent before readiness: both commands stay durable.
            assert (
                mongo_db["queued_messages"].count_documents(
                    {"link_token": "ws-tok-ready"}
                )
                == 2
            )

            # The plugin now completes the handshake: the queued commands must
            # be drained without requiring a reconnect.
            send_ready(puryfi)

            set_state_payloads: list[dict] = []
            for _ in range(100):
                message = msgpack.unpackb(puryfi.receive_bytes())
                if "type" not in message:
                    continue  # response to our own messages

                msg_type = message["type"]
                if msg_type == "getPluginIntents":
                    puryfi.send_bytes(
                        rpc_response(
                            message, {"type": "ok", "intents": INTENTS}
                        )
                    )
                elif msg_type == "getState":
                    puryfi.send_bytes(
                        rpc_response(
                            message, {"type": "ok", "value": "test-user"}
                        )
                    )
                else:
                    puryfi.send_bytes(rpc_response(message, {"type": "ok"}))

                if msg_type == "setState":
                    set_state_payloads.append(message["payload"])
                if len(set_state_payloads) == 2:
                    break

            # SDK review 6.2: the lock is configured before PuryFi is enabled.
            # SDK review 3.3: the full WriteOnlyValue<"lockConfiguration">
            # shape must reach the plugin, not just the password.
            lock_configuration = set_state_payloads[0]
            assert lock_configuration["path"] == "lockConfiguration"
            assert set(lock_configuration["value"]) == {
                "password",
                "timer",
                "timerPlus",
            }
            assert lock_configuration["value"]["password"]["secret"]
            assert lock_configuration["value"]["timer"] is None
            assert lock_configuration["value"]["timerPlus"] is None
            assert set_state_payloads[1] == {
                "path": "enabled",
                "value": True,
            }

            for _ in range(100):
                remaining = mongo_db["queued_messages"].count_documents(
                    {"link_token": "ws-tok-ready"}
                )
                if remaining == 0:
                    break
                time.sleep(0.01)
            assert remaining == 0


class TestRealtimeStatus:
    """The extension UI follows the Puryfi link without reloading the page."""

    def test_session_watcher_sees_connect_and_disconnect(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(session_id="realtime-session", link_token="rt-token")

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "realtime-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with client.websocket_connect("/ws/session/main-token") as watcher:
            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": True,
                "puryfi_version": None,
            }

            with client.websocket_connect("/ws/rt-token") as puryfi:
                send_ready(puryfi)
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                    "puryfi_version": "0.8.7.1",
                }

                # Close explicitly so the server cleanup is not canceled by
                # the TestClient context exit.
                puryfi.close()
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": False,
                    "has_linked_plugin": True,
                    "puryfi_version": None,
                }

    def test_watcher_gets_current_status_when_puryfi_is_already_online(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(session_id="realtime-session", link_token="rt-token")

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "realtime-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with client.websocket_connect("/ws/rt-token") as puryfi:
            send_ready(puryfi)
            # The first frame is the server's response to `ready`; receiving
            # it guarantees the ready state was processed.
            puryfi.receive_bytes()

            with client.websocket_connect("/ws/session/main-token") as watcher:
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                    "puryfi_version": "0.8.7.1",
                }

    def test_plugin_handshake_marks_plugin_as_linked(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(
            session_id="realtime-session",
            link_token="rt-token",
            has_linked_plugin=False,
        )

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "realtime-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with client.websocket_connect("/ws/session/main-token") as watcher:
            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": False,
                "puryfi_version": None,
            }

            with client.websocket_connect("/ws/rt-token") as puryfi:
                send_ready(puryfi)
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": False,
                    "puryfi_version": "0.8.7.1",
                }

                answer_handshake(puryfi)
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                    "puryfi_version": "0.8.7.1",
                }

                puryfi.close()
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": False,
                    "has_linked_plugin": True,
                    "puryfi_version": None,
                }

    def test_session_deleted_closes_plugin_and_watcher_sockets(
        self, client, seed_lock_configuration, mongo_db, monkeypatch
    ):
        """Ending the Chaster session must revoke the live sockets."""
        seed_lock_configuration(
            session_id="realtime-session",
            link_token="rt-token",
            has_linked_plugin=True,
        )

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "realtime-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with client.websocket_connect("/ws/session/main-token") as watcher:
            assert watcher.receive_json()["type"] == "status"

            with client.websocket_connect("/ws/rt-token") as puryfi:
                assert manager.get_by_user_link_token("rt-token") is not None
                send_ready(puryfi)
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                    "puryfi_version": "0.8.7.1",
                }

                payload = {
                    "event": "extension_session.deleted",
                    "requestId": "req-ws-del-1",
                    "data": {"session": {"sessionId": "realtime-session"}},
                }
                response = client.post(
                    WEBHOOK_URL, json=payload, auth=WEBHOOK_AUTH
                )
                assert response.status_code == 202
                wait_for_inbox(
                    mongo_db, "extension_session.deleted:realtime-session"
                )

                # Deletion publishes "offline" before closing both sockets.
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": False,
                    "has_linked_plugin": True,
                    "puryfi_version": None,
                }
                # Drain frames queued before the close (ready response, init
                # RPCs) until the close frame arrives.
                with pytest.raises(WebSocketDisconnect) as puryfi_closed:
                    for _ in range(20):
                        puryfi.receive_bytes()
                assert puryfi_closed.value.code == 4004

                with pytest.raises(WebSocketDisconnect) as watcher_closed:
                    for _ in range(20):
                        watcher.receive_json()
                assert watcher_closed.value.code == 4004

        assert manager.get_by_user_link_token("rt-token") is None

    def test_configuration_watcher_receives_status(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(session_id="realtime-session", link_token="rt-token")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"sessionId": "realtime-session", "role": "wearer"}

        class FakeChasterClient:
            async def request(self, _method: str, _url: str, **_kwargs) -> FakeResponse:
                return FakeResponse()

            async def aclose(self) -> None:
                pass

        monkeypatch.setattr(chaster_api, "chaster_client", FakeChasterClient())

        with client.websocket_connect("/ws/configuration/config-token") as watcher:
            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": True,
                "puryfi_version": None,
            }

    def test_http_status_is_online_only_after_ready(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_lock_configuration(
            session_id="ready-session", link_token="ready-token"
        )
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id="ready-session")
        )

        with client.websocket_connect("/ws/ready-token") as puryfi:
            before_ready = client.get("/api/session/main-token")
            assert before_ready.json()["is_online"] is False
            assert before_ready.json()["puryfi_version"] is None

            send_ready(puryfi)
            puryfi.receive_bytes()

            after_ready = client.get("/api/session/main-token")
            assert after_ready.json()["is_online"] is True
            assert after_ready.json()["puryfi_version"] == "0.8.7.1"

    def test_watcher_heartbeat_sends_ping(self, client, seed_lock_configuration, monkeypatch):
        seed_lock_configuration(
            session_id="heartbeat-session", link_token="heartbeat-token"
        )
        monkeypatch.setattr("routes.websocket.WATCHER_HEARTBEAT_SECONDS", 0.05)

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "heartbeat-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with client.websocket_connect("/ws/session/main-token") as watcher:
            assert watcher.receive_json()["type"] == "status"
            assert watcher.receive_json() == {"type": "ping"}

    def test_unknown_session_is_rejected(self, client, monkeypatch):
        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "missing-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/session/main-token"),
        ):
            pass

        assert exc_info.value.code == 4004
