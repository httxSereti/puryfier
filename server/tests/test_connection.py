"""Tests for Connection RPC semantics (REVIEW.md #5).

Uses a fake WebSocket so no server or DB is needed: the Connection is driven
directly through real asyncio futures.
"""

import asyncio

import msgpack
import pytest

from models.connection import Connection


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_bytes(self, data: bytes):
        self.sent.append(msgpack.unpackb(data))


class FakeLockConfig:
    link_token = "tok"
    session_id = None
    has_linked_plugin = True

    class config:
        class censorPicsConfig:
            enabled = False
            limit_count = 100
            added_duration = 600


def make_connection() -> tuple[Connection, FakeWebSocket]:
    ws = FakeWebSocket()
    return Connection(ws, FakeLockConfig()), ws


def run(coro):
    return asyncio.run(coro)


class TestSendMessageTimeout:
    def test_unanswered_rpc_times_out_and_cleans_up(self, monkeypatch):
        """An unanswered RPC must fail fast, not hang the caller forever."""
        monkeypatch.setattr(Connection, "RPC_TIMEOUT_SECONDS", 0.05)

        async def scenario():
            connection, _ = make_connection()
            with pytest.raises(asyncio.TimeoutError):
                await connection.send_message("getState", {"path": "user.username"})
            # The pending entry must not leak.
            assert connection.pending_requests == {}

        run(scenario())

    def test_answered_rpc_resolves_normally(self):
        async def scenario():
            connection, ws = make_connection()

            async def answer():
                # Wait for the outgoing RPC, then deliver its response.
                while not ws.sent:
                    await asyncio.sleep(0.001)
                await connection.handle_message(msgpack.packb({
                    "responseId": ws.sent[0]["responseId"],
                    "payload": {"type": "ok", "value": "alice"},
                }))

            result, _ = await asyncio.gather(
                connection.send_message("getState", {"path": "user.username"}),
                answer(),
            )
            assert result == {"type": "ok", "value": "alice"}
            assert connection.pending_requests == {}

        run(scenario())


class TestFailPending:
    def test_outstanding_futures_fail_on_connection_close(self):
        async def scenario():
            connection, _ = make_connection()

            task = asyncio.create_task(
                connection.send_message("enterLockPassword", {"secret": "x"})
            )
            await asyncio.sleep(0)  # let send_message register the future
            assert connection.pending_requests

            connection.fail_pending("connection closed")

            with pytest.raises(ConnectionError):
                await task
            assert connection.pending_requests == {}

        run(scenario())
