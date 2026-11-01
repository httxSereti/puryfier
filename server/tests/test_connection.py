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
    PuryfiSupportTierSchema,
    QueuedCommand,
)
from models.connection import Connection
from realtime.protocol import intents as REQUIRED_INTENTS
from realtime.protocol import optional_intents as OPTIONAL_INTENTS

READY_PAYLOAD = {
    "version": "0.8.7.1",
    "apiVersion": "1.0.0",
    "instanceId": "test-instance",
}


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.close_codes: list[int] = []

    async def send_bytes(self, data: bytes):
        self.sent.append(msgpack.unpackb(data))

    async def close(self, code: int = 1000):
        self.close_codes.append(code)


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
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []

    async def get_by_link_token(self, link_token: str) -> LockSession:
        return LockSession(
            session_id="session-1",
            config=ChasterExtensionConfigSchema(),
            link_token=link_token,
        )

    async def mark_linked(self, _link_token: str) -> bool:
        return False

    async def update(self, session_id: str, **fields) -> bool:
        self.updates.append((session_id, fields))
        return True


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


class TestPendingIntents:
    """An intents approval can take longer than the handshake itself."""

    @staticmethod
    async def _finish_handshake_without_intents(
        connection: Connection, ws: FakeWebSocket
    ) -> None:
        await connection.handle_message(
            msgpack.packb(
                {"type": "ready", "payload": READY_PAYLOAD, "responseId": 1}
            )
        )

        index = 0
        idle = 0
        while idle < 20:
            if index >= len(ws.sent):
                idle += 1
                await asyncio.sleep(0)
                continue

            idle = 0
            message = ws.sent[index]
            index += 1
            msg_type = message.get("type")
            if msg_type is None:
                continue  # response to the plugin's `ready` message

            if msg_type == "getPluginIntents":
                payload = {"type": "ok", "intents": []}
            else:
                payload = {"type": "ok"}

            await connection.handle_message(
                msgpack.packb(
                    {
                        "responseId": message["responseId"],
                        "payload": payload,
                    }
                )
            )

    def test_pending_intents_do_not_close_the_connection(self):
        async def scenario():
            connection, ws, _ = make_flush_connection()

            await self._finish_handshake_without_intents(connection, ws)
            await asyncio.sleep(0.05)

            assert connection.ready
            assert not connection.intents_granted
            assert ws.close_codes == []
            message_types = [message.get("type") for message in ws.sent]
            # Intent-gated RPCs must wait for the grant instead of failing the
            # handshake or being rejected by PuryFi.
            assert "getState" not in message_types
            assert "subscribeToState" not in message_types
            assert "subscribeToStaticMediaScans" not in message_types

            await connection.stop()

        run(scenario())

    def test_late_intents_grant_finishes_setup_and_drains_the_queue(self):
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

            await self._finish_handshake_without_intents(connection, ws)

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "intentsGrant",
                        "payload": {"intents": REQUIRED_INTENTS},
                    }
                )
            )

            index = len(ws.sent)
            for expected_type in (
                "subscribeToState",
                "getState",
                "subscribeToStaticMediaScans",
                "setState",
            ):
                await wait_until(lambda index=index: len(ws.sent) > index)
                message = ws.sent[index]
                index += 1
                assert message["type"] == expected_type

                if expected_type == "getState":
                    payload = {
                        "type": "ok",
                        "value": {
                            "username": "alice",
                            "supportTier": {"level": 2, "name": "Supporter"},
                        },
                    }
                else:
                    payload = {"type": "ok"}

                await connection.handle_message(
                    msgpack.packb(
                        {
                            "responseId": message["responseId"],
                            "payload": payload,
                        }
                    )
                )

            await wait_until(lambda: queue.messages == [])

            assert connection.intents_granted
            assert connection._intents_setup_done
            assert ws.close_codes == []
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


class FakeAutomationEngine:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []

    def has_rules(self, _session_id: str) -> bool:
        return True

    def record_event_nowait(
        self,
        _session,
        *,
        event_type: str,
        payload: dict | None = None,
        context: dict | None = None,
        event_id: str | None = None,
    ) -> bool:
        self.events.append((event_type, payload or {}, context or {}))
        return True


def make_event_connection(
    *,
    frozen: bool = False,
) -> tuple[Connection, FakeWebSocket, FakeAutomationEngine]:
    ws = FakeWebSocket()
    engine = FakeAutomationEngine()
    connection = Connection(
        ws,
        LockSession(
            session_id="session-events",
            config=ChasterExtensionConfigSchema(),
            link_token="tok-events",
            automation_mode=True,
            chaster_frozen=frozen,
        ),
        sessions=FakeSessions(),
        automation_engine=engine,
    )
    return connection, ws, engine


class TestPuryfiProtocolEvents:
    def test_ready_emits_connection_ready_event(self):
        async def scenario():
            connection, _, engine = make_event_connection()
            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "ready",
                        "payload": READY_PAYLOAD,
                        "responseId": 1,
                    }
                )
            )
            assert [event[0] for event in engine.events] == [
                "puryfi.connection.ready"
            ]
            assert engine.events[0][1]["api_version"] == "1.0.0"
            await connection.stop()

        run(scenario())

    def test_intents_revocation_clears_the_grant_without_an_event(self):
        async def scenario():
            connection, _, engine = make_event_connection()
            connection.ready = True
            connection.granted_intents = set(REQUIRED_INTENTS)
            connection.intents_granted_event.set()

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "intentsGrant",
                        "payload": {
                            "intents": [
                                intent
                                for intent in REQUIRED_INTENTS
                                if intent != "writeEnabledState"
                            ]
                        },
                    }
                )
            )

            assert engine.events == []
            assert connection.intents_granted is False
            await connection.stop()

        run(scenario())

    def test_disabled_state_change_emits_disabled_event(self):
        async def scenario():
            connection, _, engine = make_event_connection(frozen=True)
            connection.ready = True

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {"path": "enabled", "value": False},
                    }
                )
            )

            assert [event[0] for event in engine.events] == [
                "puryfi.disabled"
            ]
            _, payload, context = (
                engine.events[0][0],
                engine.events[0][1],
                engine.events[0][2],
            )
            assert payload["puryfi_enabled"] is False
            assert context["chaster_frozen"] is True
            await connection.stop()

        run(scenario())

    def test_enabled_state_change_emits_enabled_event(self):
        async def scenario():
            connection, _, engine = make_event_connection()
            connection.ready = True

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {"path": "enabled", "value": True},
                    }
                )
            )

            assert [event[0] for event in engine.events] == [
                "puryfi.enabled"
            ]
            assert engine.events[0][1]["puryfi_enabled"] is True
            await connection.stop()

        run(scenario())

    def test_lock_configuration_change_emits_locked_and_unlocked_events(self):
        async def scenario():
            connection, _, engine = make_event_connection()
            connection.ready = True

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "lockConfiguration",
                            "value": {"password": "secret"},
                        },
                    }
                )
            )
            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "lockConfiguration",
                            "value": None,
                        },
                    }
                )
            )

            assert [event[0] for event in engine.events] == [
                "puryfi.locked",
                "puryfi.unlocked",
            ]
            assert [event[1]["puryfi_has_lock"] for event in engine.events] == [
                True,
                False,
            ]
            await connection.stop()

        run(scenario())

    def test_user_state_change_updates_profile_without_emitting_an_event(self):
        async def scenario():
            connection, _, engine = make_event_connection()
            connection.ready = True

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "user",
                            "value": {
                                "username": "alice",
                                "supportTier": {
                                    "level": 2,
                                    "name": "Supporter",
                                },
                            },
                        },
                    }
                )
            )
            await wait_until(
                lambda: connection.session.puryfi_username == "alice"
            )

            assert engine.events == []
            assert connection.session.puryfi_username == "alice"
            await connection.stop()

        run(scenario())

    def test_notify_disconnected_emits_event_when_frozen(self):
        async def scenario():
            connection, _, engine = make_event_connection(frozen=True)
            connection.ready = True

            connection.notify_disconnected()

            assert [event[0] for event in engine.events] == [
                "puryfi.connection.disconnected"
            ]
            assert engine.events[0][2]["chaster_frozen"] is True
            await connection.stop()

        run(scenario())


class TestPuryfiProfile:
    """The profile is diagnostic metadata: never block the handshake on it."""

    @staticmethod
    def _connection(sessions: FakeSessions) -> tuple[Connection, FakeWebSocket]:
        ws = FakeWebSocket()
        connection = Connection(
            ws,
            LockSession(
                session_id="session-1",
                config=ChasterExtensionConfigSchema(),
                link_token="tok",
            ),
            sessions=sessions,
        )
        connection.ready = True
        return connection, ws

    @staticmethod
    async def _answer_handshake(
        connection: Connection,
        ws: FakeWebSocket,
        *,
        user_response: dict,
        username_response: dict,
        support_tier_response: dict,
        puryfi_intents: list[str] | None = None,
        enabled_response: dict | None = None,
        lock_response: dict | None = None,
    ) -> list[dict]:
        """Answer the init RPCs until the scan subscription completes."""
        messages: list[dict] = []
        index = 0
        intents_response = (
            REQUIRED_INTENTS if puryfi_intents is None else puryfi_intents
        )

        while True:
            await wait_until(lambda index=index: len(ws.sent) > index)
            message = ws.sent[index]
            messages.append(message)
            msg_type = message["type"]
            path = message["payload"].get("path")

            if msg_type == "getPluginIntents":
                payload = {"type": "ok", "intents": intents_response}
            elif msg_type == "getState" and path == "user":
                payload = user_response
            elif msg_type == "getState" and path == "user.username":
                payload = username_response
            elif msg_type == "getState" and path == "user.supportTier":
                payload = support_tier_response
            elif msg_type == "getState" and path == "enabled":
                payload = enabled_response or {"type": "ok", "value": None}
            elif msg_type == "getState" and path == "lockConfiguration":
                payload = lock_response or {"type": "ok", "value": None}
            else:
                payload = {"type": "ok"}

            await connection.handle_message(
                msgpack.packb(
                    {
                        "responseId": message["responseId"],
                        "payload": payload,
                    }
                )
            )
            index += 1

            if msg_type == "subscribeToStaticMediaScans":
                return messages

    def test_initialize_plugin_persists_username_and_support_tier(self):
        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)

            initialized, messages = await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    user_response={
                        "type": "ok",
                        "value": {
                            "username": "alice",
                            "supportTier": {"level": 2, "name": "Supporter"},
                        },
                    },
                    username_response={"type": "ok", "value": "alice"},
                    support_tier_response={
                        "type": "ok",
                        "value": {"level": 2, "name": "Supporter"},
                    },
                ),
            )

            assert initialized is True
            assert connection.username == "alice"
            assert connection.session.puryfi_username == "alice"
            assert connection.session.puryfi_support_tier == (
                PuryfiSupportTierSchema(level=2, name="Supporter")
            )
            assert ("subscribeToState", {"path": "user"}) in [
                (message["type"], message["payload"]) for message in messages
            ]
            assert sessions.updates == [
                (
                    "session-1",
                    {
                        "puryfi_username": "alice",
                        "puryfi_support_tier": PuryfiSupportTierSchema(
                            level=2, name="Supporter"
                        ),
                    },
                )
            ]
            await connection.stop()

        run(scenario())

    def test_initialize_plugin_reads_optional_puryfi_state(self):
        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)
            optional = [*REQUIRED_INTENTS, *OPTIONAL_INTENTS]

            initialized, _ = await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    puryfi_intents=optional,
                    user_response={
                        "type": "ok",
                        "value": {
                            "username": "alice",
                            "supportTier": {"level": 2, "name": "Supporter"},
                        },
                    },
                    username_response={"type": "ok", "value": "alice"},
                    support_tier_response={"type": "ok", "value": {}},
                    enabled_response={"type": "ok", "value": True},
                    lock_response={
                        "type": "ok",
                        "value": {"startTime": 1000},
                    },
                ),
            )

            assert initialized is True
            assert connection.puryfi_enabled is True
            assert connection.puryfi_has_lock is True
            await connection.stop()

        run(scenario())

    def test_state_change_updates_the_optional_puryfi_state(self):
        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)
            optional = [*REQUIRED_INTENTS, *OPTIONAL_INTENTS]

            await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    puryfi_intents=optional,
                    user_response={"type": "ok", "value": None},
                    username_response={"type": "error"},
                    support_tier_response={"type": "error"},
                    enabled_response={"type": "ok", "value": True},
                    lock_response={
                        "type": "ok",
                        "value": {"startTime": 1000},
                    },
                ),
            )

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {"path": "enabled", "value": False},
                    }
                )
            )
            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "lockConfiguration",
                            "value": None,
                        },
                    }
                )
            )
            await wait_until(
                lambda: connection.puryfi_enabled is False
                and connection.puryfi_has_lock is False
            )

            await connection.stop()

        run(scenario())

    def test_profile_error_does_not_fail_the_handshake(self):
        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)

            initialized, _ = await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    user_response={
                        "type": "error",
                        "error": "unavailablePath",
                        "message": "user is null",
                    },
                    username_response={"type": "ok", "value": "alice"},
                    support_tier_response={
                        "type": "error",
                        "message": "unknown path",
                    },
                ),
            )

            assert initialized is True
            assert connection.session.puryfi_username == "alice"
            assert connection.session.puryfi_support_tier is None
            assert sessions.updates == [
                ("session-1", {"puryfi_username": "alice"})
            ]
            await connection.stop()

        run(scenario())

    def test_late_user_load_is_captured_after_a_null_handshake(self):
        """PuryFi can expose `user` as null while the account is loading."""

        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)

            initialized, _ = await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    user_response={"type": "ok", "value": None},
                    username_response={
                        "type": "error",
                        "error": "unavailablePath",
                    },
                    support_tier_response={
                        "type": "error",
                        "error": "unavailablePath",
                    },
                ),
            )

            assert initialized is True
            assert connection.session.puryfi_username is None
            assert sessions.updates == []

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "user",
                            "value": {
                                "username": "alice",
                                "supportTier": {"level": 2, "name": "Supporter"},
                            },
                        },
                    }
                )
            )
            await wait_until(lambda: bool(sessions.updates))

            assert connection.session.puryfi_username == "alice"
            assert connection.session.puryfi_support_tier == (
                PuryfiSupportTierSchema(level=2, name="Supporter")
            )
            await connection.stop()

        run(scenario())

    def test_user_state_change_refreshes_the_profile(self):
        async def scenario():
            sessions = FakeSessions()
            connection, ws = self._connection(sessions)

            await asyncio.gather(
                connection.initialize_plugin(),
                self._answer_handshake(
                    connection,
                    ws,
                    user_response={
                        "type": "ok",
                        "value": {
                            "username": "alice",
                            "supportTier": {"level": 2, "name": "Supporter"},
                        },
                    },
                    username_response={"type": "ok", "value": "alice"},
                    support_tier_response={"type": "ok", "value": {}},
                ),
            )
            sessions.updates.clear()

            await connection.handle_message(
                msgpack.packb(
                    {
                        "type": "stateChange",
                        "payload": {
                            "path": "user",
                            "value": {
                                "username": "bob",
                                "supportTier": {"level": 3, "name": "Gold"},
                            },
                        },
                    }
                )
            )
            await wait_until(lambda: bool(sessions.updates))

            assert connection.username == "bob"
            assert connection.session.puryfi_username == "bob"
            assert connection.session.puryfi_support_tier == (
                PuryfiSupportTierSchema(level=3, name="Gold")
            )
            assert sessions.updates == [
                (
                    "session-1",
                    {
                        "puryfi_username": "bob",
                        "puryfi_support_tier": PuryfiSupportTierSchema(
                            level=3, name="Gold"
                        ),
                    },
                )
            ]
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
            connection._handshake_completed = True
            connection._intents_setup_done = True

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
