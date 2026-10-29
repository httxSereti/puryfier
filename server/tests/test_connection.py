"""Tests for Connection RPC semantics (REVIEW.md #5).

Uses a fake WebSocket so no server or DB is needed: the Connection is driven
directly through real asyncio futures.
"""

import asyncio

import msgpack
import pytest

from domain.entities import (
    ChasterExtensionConfigSchema,
    LockSession,
    QueuedCommand,
)
from models.connection import Connection
from realtime.protocol import intents as REQUIRED_INTENTS

READY_PAYLOAD = {
    "version": "0.8.7.1",
    "apiVersion": "1.0.0",
    "instanceId": "test-instance",
}


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_bytes(self, data: bytes):
        self.sent.append(msgpack.unpackb(data))


class FakeQueue:
    def __init__(self, messages: list[QueuedCommand]):
        self.messages = list(messages)
        self.deleted: list[QueuedCommand] = []

    async def fetch(self, _link_token: str) -> list[QueuedCommand]:
        return list(self.messages)

    async def delete(self, command: QueuedCommand) -> None:
        self.deleted.append(command)
        self.messages.remove(command)


class FakeSessions:
    async def get_by_link_token(self, link_token: str) -> LockSession:
        return LockSession(
            session_id="session-1",
            config=ChasterExtensionConfigSchema(),
            link_token=link_token,
        )

    async def mark_linked(self, _link_token: str) -> bool:
        return False


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


async def wait_until(predicate, attempts: int = 100) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


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
            await connection.stop()

        run(scenario())

    def test_answered_rpc_resolves_normally(self):
        async def scenario():
            connection, ws = make_connection()

            async def answer():
                # Wait for the outgoing RPC, then deliver its response.
                await wait_until(lambda: bool(ws.sent))
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
            await connection.stop()

        run(scenario())


class TestMailbox:
    def test_sends_are_serialized_in_submission_order(self):
        async def scenario():
            connection, ws = make_connection()
            tasks = [
                asyncio.create_task(
                    connection.send_message("setState", {"path": f"p{index}"})
                )
                for index in range(3)
            ]

            await wait_until(lambda: bool(ws.sent))
            # Only the first command may be in flight: the mailbox worker
            # waits for its response before sending the next one.
            assert [message["payload"]["path"] for message in ws.sent] == ["p0"]

            for index in range(3):
                await wait_until(lambda index=index: len(ws.sent) > index)
                await connection.handle_message(
                    msgpack.packb(
                        {
                            "responseId": ws.sent[index]["responseId"],
                            "payload": {"type": "ok"},
                        }
                    )
                )

            results = await asyncio.gather(*tasks)
            assert [result["type"] for result in results] == ["ok", "ok", "ok"]
            assert [
                message["payload"]["path"] for message in ws.sent
            ] == ["p0", "p1", "p2"]
            await connection.stop()

        run(scenario())

    def test_batch_is_sent_in_order(self):
        async def scenario():
            connection, ws = make_connection()
            task = asyncio.create_task(
                connection.send_messages(
                    [("first", {"value": 1}), ("second", {"value": 2})]
                )
            )

            for index, expected_type in enumerate(("first", "second")):
                await wait_until(lambda index=index: len(ws.sent) > index)
                assert ws.sent[index]["type"] == expected_type
                await connection.handle_message(
                    msgpack.packb(
                        {
                            "responseId": ws.sent[index]["responseId"],
                            "payload": {"type": "ok", "index": index},
                        }
                    )
                )

            results = await task
            assert [result["index"] for result in results] == [0, 1]
            await connection.stop()

        run(scenario())

    def test_stop_fails_inflight_rpc_with_connection_error(self):
        async def scenario():
            connection, _ = make_connection()
            task = asyncio.create_task(
                connection.send_message("enterLockPassword", {"secret": "x"})
            )
            await wait_until(lambda: bool(connection.pending_requests))

            await connection.stop()

            with pytest.raises(ConnectionError):
                await task
            assert connection._worker_task is None

        run(scenario())

    def test_configuration_update_goes_through_the_mailbox(self):
        async def scenario():
            connection, _ = make_connection()
            config = ChasterExtensionConfigSchema(lock_on_freeze=True)

            await connection.update_configuration(config)

            assert connection.user_lock_config.config is config
            await connection.stop()

        run(scenario())

    def test_queued_commands_fail_when_connection_closes(self):
        async def scenario():
            connection, _ = make_connection()
            tasks = [
                asyncio.create_task(
                    connection.send_message("setState", {"path": f"p{index}"})
                )
                for index in range(3)
            ]
            await asyncio.sleep(0)

            connection.fail_pending("connection closed")

            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(isinstance(result, ConnectionError) for result in results)
            assert connection.pending_requests == {}
            await connection.stop()

        run(scenario())


class TestReadyGuard:
    def test_ready_ack_is_sent_before_handshake_rpcs(self):
        """PuryFi ignores plugin frames until it received the ready ack."""

        async def scenario():
            connection, ws = make_connection()

            await connection.handle_message(
                msgpack.packb(
                    {"type": "ready", "payload": READY_PAYLOAD, "responseId": 42}
                )
            )
            await wait_until(
                lambda: any(
                    message.get("type") == "setPluginManifest"
                    for message in ws.sent
                )
            )

            assert ws.sent[0] == {
                "payload": {"type": "ok"},
                "responseId": 42,
            }
            assert connection.ready
            assert connection.puryfi_version == "0.8.7.1"
            assert connection.api_version == "1.0.0"
            assert connection.instance_id == "test-instance"
            await connection.stop()

        run(scenario())

    def test_duplicate_ready_starts_one_handshake(self):
        async def scenario():
            connection, ws = make_connection()

            await connection.handle_message(
                msgpack.packb(
                    {"type": "ready", "payload": READY_PAYLOAD, "responseId": 1}
                )
            )
            await connection.handle_message(
                msgpack.packb(
                    {"type": "ready", "payload": READY_PAYLOAD, "responseId": 2}
                )
            )
            await wait_until(
                lambda: any(
                    message.get("type") == "setPluginManifest"
                    for message in ws.sent
                )
            )
            await asyncio.sleep(0)

            assert sum(
                message.get("type") == "setPluginManifest"
                for message in ws.sent
            ) == 1
            assert connection.ready
            await connection.stop()

        run(scenario())

    @pytest.mark.parametrize(
        "api_version",
        ["1.0.0", "1.4.2", "1.99.999"],
        ids=["minimum", "patch", "upper-edge"],
    )
    def test_compatible_api_version_is_acknowledged(self, api_version):
        """SDK review 3.4: the [1.0.0, 2.0.0) range must be accepted."""

        async def scenario():
            connection, ws = make_connection()
            payload = {**READY_PAYLOAD, "apiVersion": api_version}

            await connection.handle_message(
                msgpack.packb(
                    {"type": "ready", "payload": payload, "responseId": 11}
                )
            )
            await wait_until(
                lambda: any(
                    message.get("type") == "setPluginManifest"
                    for message in ws.sent
                )
            )

            assert ws.sent[0] == {
                "payload": {"type": "ok"},
                "responseId": 11,
            }
            assert connection.ready
            assert connection.api_version == api_version
            await connection.stop()

        run(scenario())

    @pytest.mark.parametrize(
        "api_version",
        ["0.9.9", "2.0.0", "2.1.0", "1.0", "1.0.0.0", "one.0.0", None],
        ids=[
            "below-minimum",
            "maximum-exclusive",
            "above-maximum",
            "missing-patch",
            "extra-part",
            "non-numeric",
            "missing",
        ],
    )
    def test_incompatible_api_version_is_refused_without_handshake(self, api_version):
        """SDK review 3.4: errors use `name`, and no handshake may start."""

        async def scenario():
            connection, ws = make_connection()
            payload = {**READY_PAYLOAD, "apiVersion": api_version}

            await connection.handle_message(
                msgpack.packb(
                    {"type": "ready", "payload": payload, "responseId": 12}
                )
            )

            assert len(ws.sent) == 1
            response = ws.sent[0]
            assert response["responseId"] == 12
            assert response["payload"]["type"] == "error"
            assert response["payload"]["name"] == "incompatibleApiVersion"
            assert "[1.0.0, 2.0.0)" in response["payload"]["message"]
            assert not connection.ready
            # Metadata is still kept for diagnostics.
            assert connection.puryfi_version == "0.8.7.1"
            assert connection.instance_id == "test-instance"

            # No handshake RPC may be sent after the refused ready.
            await asyncio.sleep(0)
            assert len(ws.sent) == 1
            await connection.stop()

        run(scenario())

    def test_compatible_ready_after_incompatible_one_starts_handshake(self):
        async def scenario():
            connection, ws = make_connection()

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "ready",
                        "payload": {**READY_PAYLOAD, "apiVersion": "2.0.0"},
                        "responseId": 1,
                    }
                )
            )
            assert not connection.ready

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "ready",
                        "payload": {**READY_PAYLOAD, "apiVersion": "1.2.3"},
                        "responseId": 2,
                    }
                )
            )
            await wait_until(
                lambda: any(
                    message.get("type") == "setPluginManifest"
                    for message in ws.sent
                )
            )

            assert connection.ready
            assert ws.sent[1] == {
                "payload": {"type": "ok"},
                "responseId": 2,
            }
            await connection.stop()

        run(scenario())

    def test_intents_wait_has_a_timeout(self, monkeypatch):
        monkeypatch.setattr(Connection, "INTENTS_TIMEOUT_SECONDS", 0.05)

        async def scenario():
            connection, _ = make_connection()
            loop = asyncio.get_running_loop()
            started = loop.time()

            await connection.process_queued_messages("tok")

            assert loop.time() - started < 0.5
            await connection.stop()

        run(scenario())


class TestFailPending:
    def test_outstanding_futures_fail_on_connection_close(self):
        async def scenario():
            connection, _ = make_connection()

            task = asyncio.create_task(
                connection.send_message("enterLockPassword", {"secret": "x"})
            )
            await wait_until(lambda: bool(connection.pending_requests))
            assert connection.pending_requests

            connection.fail_pending("connection closed")

            with pytest.raises(ConnectionError):
                await task
            assert connection.pending_requests == {}
            await connection.stop()

        run(scenario())


def make_flush_connection(
    messages: list[QueuedCommand] | None = None,
) -> tuple[Connection, FakeWebSocket, FakeQueue]:
    ws = FakeWebSocket()
    queue = FakeQueue(messages or [])
    connection = Connection(
        ws,
        FakeLockConfig(),
        sessions=FakeSessions(),
        queue=queue,
    )
    return connection, ws, queue


async def answer_rpcs(connection: Connection, ws: FakeWebSocket, responses: list[dict]):
    """Answer the next outgoing RPCs in order."""
    for index, payload in enumerate(responses):
        await wait_until(lambda index=index: len(ws.sent) > index)
        await connection.handle_message(
            msgpack.packb(
                {
                    "responseId": ws.sent[index]["responseId"],
                    "payload": payload,
                }
            )
        )


class TestQueueFlushReadiness:
    """Commands must never be sent before ready + intentsGrant (SDK review 3.1)."""

    def test_flush_is_a_noop_before_ready(self):
        async def scenario():
            connection, ws, queue = make_flush_connection(
                [QueuedCommand(id="1", link_token="tok", msg_type="setState", payload={})]
            )

            assert await connection.flush_queue() is False
            assert ws.sent == []
            assert len(queue.messages) == 1  # nothing lost
            await connection.stop()

        run(scenario())

    def test_flush_is_a_noop_before_intents_grant(self):
        async def scenario():
            connection, ws, queue = make_flush_connection(
                [QueuedCommand(id="1", link_token="tok", msg_type="setState", payload={})]
            )
            connection.ready = True

            assert await connection.flush_queue() is False
            assert ws.sent == []
            assert len(queue.messages) == 1
            await connection.stop()

        run(scenario())

    def test_flush_delivers_in_order_once_ready_and_granted(self):
        async def scenario():
            messages = [
                QueuedCommand(
                    id="1",
                    link_token="tok",
                    msg_type="enterLockPassword",
                    payload={"secret": "s3cret"},
                ),
                QueuedCommand(
                    id="2",
                    link_token="tok",
                    msg_type="setState",
                    payload={"path": "enabled", "value": False},
                ),
            ]
            connection, ws, queue = make_flush_connection(messages)
            connection.ready = True
            connection.intents_granted_event.set()

            delivered, _ = await asyncio.gather(
                connection.flush_queue(),
                answer_rpcs(
                    connection,
                    ws,
                    [{"type": "ok"}, {"type": "ok"}],
                ),
            )

            assert delivered is True
            assert [message["type"] for message in ws.sent] == [
                "enterLockPassword",
                "setState",
            ]
            assert queue.messages == []
            assert len(queue.deleted) == 2
            await connection.stop()

        run(scenario())

    def test_lock_configuration_error_never_enables_puryfi(self):
        """SDK review 6.2: failed lockConfiguration must stop the sequence."""

        async def scenario():
            messages = [
                QueuedCommand(
                    id="1",
                    link_token="tok",
                    msg_type="setState",
                    payload={
                        "path": "lockConfiguration",
                        "value": {
                            "password": {"secret": "s3cret"},
                            "timer": None,
                            "timerPlus": None,
                        },
                    },
                ),
                QueuedCommand(
                    id="2",
                    link_token="tok",
                    msg_type="setState",
                    payload={"path": "enabled", "value": True},
                ),
            ]
            connection, ws, queue = make_flush_connection(messages)
            connection.ready = True
            connection.intents_granted_event.set()

            delivered, _ = await asyncio.gather(
                connection.flush_queue(),
                answer_rpcs(
                    connection,
                    ws,
                    [
                        {
                            "type": "error",
                            "error": "invalidMessage",
                            "message": "bad lock configuration",
                        }
                    ],
                ),
            )

            assert delivered is False
            assert [message["payload"]["path"] for message in ws.sent] == [
                "lockConfiguration"
            ]
            # Nothing was acknowledged: both commands stay queued in order and
            # can be replayed on the next drain.
            assert [command.id for command in queue.messages] == ["1", "2"]
            assert queue.deleted == []
            await connection.stop()

        run(scenario())

    def test_intents_grant_triggers_the_pending_queue_drain(self):
        async def scenario():
            connection, ws, queue = make_flush_connection(
                [
                    QueuedCommand(
                        id="1",
                        link_token="tok",
                        msg_type="setState",
                        payload={"path": "enabled", "value": True},
                    )
                ]
            )
            connection.ready = True

            assert await connection.flush_queue() is False
            assert queue.messages

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "intentsGrant",
                        "payload": {"intents": REQUIRED_INTENTS},
                    }
                )
            )

            await asyncio.wait_for(answer_rpcs(connection, ws, [{"type": "ok"}]), 1)
            for _ in range(100):
                if not queue.messages:
                    break
                await asyncio.sleep(0.01)

            assert queue.messages == []
            assert [message["type"] for message in ws.sent] == ["setState"]
            await connection.stop()

        run(scenario())

    @pytest.mark.parametrize(
        "error_payload",
        [
            {
                "type": "error",
                "error": "missingPluginIntents",
                "message": "intents required",
            },
            {
                "type": "error",
                "error": "missingIntents",
                "message": "intents required",
            },
            {
                "type": "error",
                "name": "missingPluginIntents",
                "message": "intents required",
            },
            {
                "type": "error",
                "name": "missingIntents",
                "message": "intents required",
            },
        ],
        ids=[
            "runtime-missingPluginIntents",
            "runtime-missingIntents",
            "sdk-missingPluginIntents",
            "sdk-missingIntents",
        ],
    )
    def test_missing_intents_error_keeps_the_command_queued(self, error_payload):
        async def scenario():
            connection, ws, queue = make_flush_connection(
                [
                    QueuedCommand(
                        id="1",
                        link_token="tok",
                        msg_type="setState",
                        payload={"path": "enabled", "value": True},
                    )
                ]
            )
            connection.ready = True
            connection.intents_granted_event.set()

            delivered, _ = await asyncio.gather(
                connection.flush_queue(),
                answer_rpcs(
                    connection,
                    ws,
                    [
                        error_payload,
                        {"type": "ok"},
                    ],
                ),
            )

            assert delivered is False
            assert queue.messages  # still queued for the next drain
            assert [message["type"] for message in ws.sent] == [
                "setState",
                "requestPluginIntents",
            ]
            await connection.stop()

        run(scenario())

    def test_other_errors_keep_the_command_queued_without_re_requesting_intents(self):
        async def scenario():
            connection, ws, queue = make_flush_connection(
                [
                    QueuedCommand(
                        id="1",
                        link_token="tok",
                        msg_type="setState",
                        payload={"path": "enabled", "value": True},
                    )
                ]
            )
            connection.ready = True
            connection.intents_granted_event.set()

            delivered, _ = await asyncio.gather(
                connection.flush_queue(),
                answer_rpcs(
                    connection,
                    ws,
                    [{"type": "error", "error": "invalidPath", "message": "nope"}],
                ),
            )

            assert delivered is False
            assert queue.messages
            assert [message["type"] for message in ws.sent] == ["setState"]
            await connection.stop()

        run(scenario())
