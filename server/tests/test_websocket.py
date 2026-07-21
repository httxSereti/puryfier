"""E2E tests for the Puryfi WebSocket endpoint (REVIEW.md #6, #9).

Drives the real endpoint with a fake Puryfi client speaking msgpack through
the FastAPI TestClient, against the in-memory Mongo.
"""

import time

import msgpack
import pytest
from starlette.websockets import WebSocketDisconnect

from models.connection_manager import manager

INTENTS = [
    "readUserState",
    "writeLockConfigurationState",
    "writeEnabledState",
    "readMediaProcesses",
]


@pytest.fixture(autouse=True)
def clean_manager():
    """The ConnectionManager is a process-wide singleton: isolate tests."""
    manager._connections.clear()
    yield
    manager._connections.clear()


def rpc_response(request_msg: dict, payload: dict) -> bytes:
    return msgpack.packb({"responseId": request_msg["responseId"], "payload": payload})


class TestLifecycle:
    def test_unknown_token_is_rejected(self, client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/no-such-token"):
                pass
        assert exc_info.value.code == 4004

    def test_connection_registered_then_removed_on_disconnect(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(link_token="ws-tok-1", session_id=None)

        with client.websocket_connect("/ws-tok-1"):
            assert manager.get_by_user_link_token("ws-tok-1") is not None

        assert manager.get_by_user_link_token("ws-tok-1") is None

    def test_malformed_frame_removes_connection(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(link_token="ws-tok-2", session_id=None)

        with client.websocket_connect("/ws-tok-2") as ws:
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
        seed_lock_configuration(link_token="ws-tok-3", session_id=None)
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

        with client.websocket_connect("/ws-tok-3") as ws:
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
        seed_lock_configuration(link_token="ws-tok-4", session_id=None)
        mongo_db["queued_messages"].insert_one({
            "link_token": "ws-tok-4",
            "msg_type": "setState",
            "payload": {"path": "enabled", "value": True},
            "created_at": "2026-01-01T00:00:01Z",
        })

        with client.websocket_connect("/ws-tok-4") as ws:
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
