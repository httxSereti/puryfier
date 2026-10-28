"""E2E tests for the Puryfi WebSocket endpoint (REVIEW.md #6, #9).

Drives the real endpoint with a fake Puryfi client speaking msgpack through
the FastAPI TestClient, against the in-memory Mongo.
"""

import time

import msgpack
import pytest
from conftest import WEBHOOK_AUTH
from starlette.websockets import WebSocketDisconnect
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


@pytest.fixture(autouse=True)
def clean_manager():
    """The ConnectionManager and watchers are process-wide singletons: isolate tests."""
    manager._connections.clear()
    watchers._watchers.clear()
    yield
    manager._connections.clear()
    watchers._watchers.clear()


def rpc_response(request_msg: dict, payload: dict) -> bytes:
    return msgpack.packb({"responseId": request_msg["responseId"], "payload": payload})


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

        with client.websocket_connect("/ws/ws-tok-1"):
            assert manager.get_by_user_link_token("ws-tok-1") is not None

        assert manager.get_by_user_link_token("ws-tok-1") is None

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
            ws.send_bytes(msgpack.packb({"type": "ready", "payload": {}, "responseId": 999}))

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
            ws.send_bytes(msgpack.packb({"type": "ready", "payload": {}, "responseId": 999}))

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
            }

            with client.websocket_connect("/ws/rt-token"):
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                }

            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": True,
            }

    def test_watcher_gets_current_status_when_puryfi_is_already_online(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(session_id="realtime-session", link_token="rt-token")

        async def fake_get_session_auth(_main_token: str) -> dict:
            return {"role": "wearer", "session": {"sessionId": "realtime-session"}}

        monkeypatch.setattr(chaster_api, "get_session_auth", fake_get_session_auth)

        with (
            client.websocket_connect("/ws/rt-token"),
            client.websocket_connect("/ws/session/main-token") as watcher,
        ):
            assert watcher.receive_json() == {
                "type": "status",
                "is_online": True,
                "has_linked_plugin": True,
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
            }

            with client.websocket_connect("/ws/rt-token") as puryfi:
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": False,
                }

                puryfi.send_bytes(
                    msgpack.packb({"type": "ready", "payload": {}, "responseId": 999})
                )
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                }

            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": True,
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

                # The plugin connection published "online"; deletion then
                # publishes "offline" before closing both sockets.
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": True,
                    "has_linked_plugin": True,
                }
                assert watcher.receive_json() == {
                    "type": "status",
                    "is_online": False,
                    "has_linked_plugin": True,
                }
                with pytest.raises(WebSocketDisconnect) as puryfi_closed:
                    puryfi.receive_bytes()
                assert puryfi_closed.value.code == 4004

                with pytest.raises(WebSocketDisconnect) as watcher_closed:
                    watcher.receive_json()
                assert watcher_closed.value.code == 4004

        assert manager.get_by_user_link_token("rt-token") is None

    def test_configuration_watcher_receives_status(
        self, client, seed_lock_configuration, monkeypatch
    ):
        seed_lock_configuration(session_id="realtime-session", link_token="rt-token")

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"sessionId": "realtime-session", "role": "wearer"}

        class FakeChasterClient:
            async def get(self, _url: str) -> FakeResponse:
                return FakeResponse()

            async def aclose(self) -> None:
                pass

        monkeypatch.setattr(chaster_api, "chaster_client", FakeChasterClient())

        with client.websocket_connect("/ws/configuration/config-token") as watcher:
            assert watcher.receive_json() == {
                "type": "status",
                "is_online": False,
                "has_linked_plugin": True,
            }

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
