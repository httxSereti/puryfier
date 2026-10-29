"""One supervised actor per Puryfi WebSocket connection."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from fastapi import WebSocket

from domain.entities import ChasterExtensionConfigSchema, LockSession
from domain.ports import LockSessionRepository, MessageQueue
from domain.use_cases.media_scan import CENSORABLE_LABELS, MediaScanService
from infra.chaster import ChasterService, add_time_to_lock, create_custom_log
from infra.logging import get_logger
from infra.queue import MongoMessageQueue
from infra.repositories import MongoLockSessionRepository
from realtime.protocol import decode, encode, intents, manifest
from workers.outbound import drain_queued_messages

log = get_logger(__name__)

__all__ = [
    "CENSORABLE_LABELS",
    "Connection",
    "add_time_to_lock",
    "create_custom_log",
    "intents",
    "manifest",
]


@dataclass
class _SendCommand:
    messages: list[tuple[str, dict]]
    future: asyncio.Future[list[dict]]


@dataclass
class _UpdateConfigCommand:
    config: ChasterExtensionConfigSchema
    future: asyncio.Future[None]


_MailboxCommand = _SendCommand | _UpdateConfigCommand

StatusPublisher = Callable[["Connection"], Awaitable[None]]


class Connection:
    def __init__(
        self,
        websocket: WebSocket,
        user_lock_config: LockSession,
        *,
        sessions: LockSessionRepository | None = None,
        queue: MessageQueue | None = None,
        media_scans: MediaScanService | None = None,
    ):
        self.websocket = websocket
        self.session: LockSession = user_lock_config
        self.next_response_id = 0
        self.pending_requests = {}

        self.configuration: dict = {}

        self.username: str | None = None
        self.ready = False

        self.intents_granted_event = asyncio.Event()
        self._ready_handled = False
        self._tasks: set[asyncio.Task] = set()

        self._sessions = sessions or MongoLockSessionRepository()
        self._queue = queue or MongoMessageQueue()
        self._media_scans = media_scans or MediaScanService(
            sessions=self._sessions,
            chaster=ChasterService(),
        )
        self._status_publisher: StatusPublisher | None = None

        # One ordered mailbox per connection: every outbound command is queued
        # here and sent by a single worker. This serializes sends and keeps
        # responseId correlation unambiguous.
        self._mailbox: asyncio.Queue[_MailboxCommand] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False

    # Seconds to wait for a Puryfi client response before failing the RPC.
    RPC_TIMEOUT_SECONDS = 15.0
    INTENTS_TIMEOUT_SECONDS = 30.0
    HANDSHAKE_TIMEOUT_SECONDS = 60.0

    # Compatibility aliases for the pre-P2 Connection API.
    @property
    def user_lock_config(self) -> LockSession:
        return self.session

    @user_lock_config.setter
    def user_lock_config(self, value: LockSession) -> None:
        self.session = value

    @property
    def user_link_token(self) -> str:
        return self.session.link_token or ""

    @property
    def seen_censored_objects(self) -> int:
        return getattr(self.session, "seen_censored_objects", 0) or 0

    @seen_censored_objects.setter
    def seen_censored_objects(self, value: int) -> None:
        self.session.seen_censored_objects = value

    def set_status_publisher(self, publisher: StatusPublisher) -> None:
        self._status_publisher = publisher

    async def _publish_status(self) -> None:
        if self._status_publisher is not None:
            await self._status_publisher(self)

    async def start(self) -> None:
        """Start the connection actor (idempotent)."""
        self._closed = False
        self._ensure_worker()

    async def stop(self) -> None:
        """Stop the actor, its supervised tasks, and every pending RPC."""
        if self._closed:
            return

        self._closed = True
        self.ready = False

        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

        task = self._worker_task
        self._worker_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self.fail_pending("connection closed")

    def _spawn(self, coro, name: str) -> asyncio.Task:
        """Supervise a background task for the lifetime of the connection."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error(
                "connection.task_failed",
                task=task.get_name(),
                error=type(exc).__name__,
                exc_info=exc,
            )

    def _ensure_worker(self) -> None:
        if self._closed:
            raise ConnectionError("connection is closed")
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._run_mailbox(), name="puryfi-connection-mailbox"
            )

    async def send_message(self, msg_type: str, payload: dict) -> dict:
        """Send one RPC through the ordered mailbox."""
        results = await self.send_messages([(msg_type, payload)])
        return results[0]

    async def send_messages(self, messages: list[tuple[str, dict]]) -> list[dict]:
        """Atomically enqueue several RPCs and await all their responses."""
        if not messages:
            return []

        future: asyncio.Future[list[dict]] = (
            asyncio.get_running_loop().create_future()
        )
        self._ensure_worker()
        await self._mailbox.put(_SendCommand(messages=list(messages), future=future))
        return await future

    async def update_configuration(
        self, config: ChasterExtensionConfigSchema
    ) -> None:
        """Update the cached config through the mailbox (ordered with sends)."""
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._ensure_worker()
        await self._mailbox.put(_UpdateConfigCommand(config=config, future=future))
        await future

    async def _run_mailbox(self) -> None:
        while True:
            command = await self._mailbox.get()
            try:
                if isinstance(command, _SendCommand):
                    results = [
                        await self._send_message_now(msg_type, payload)
                        for msg_type, payload in command.messages
                    ]
                    if not command.future.done():
                        command.future.set_result(results)
                else:
                    self.session.config = command.config
                    if not command.future.done():
                        command.future.set_result(None)
            except asyncio.CancelledError:
                # Do not propagate CancelledError to the webhook/queue caller:
                # a closing socket is a normal ConnectionError, not a reason to
                # cancel the durable webhook worker.
                if not command.future.done():
                    command.future.set_exception(
                        ConnectionError("connection closed")
                    )
                raise
            except Exception as exc:  # noqa: BLE001 - deliver to the caller
                if not command.future.done():
                    command.future.set_exception(exc)
            finally:
                self._mailbox.task_done()

    async def _send_message_now(self, msg_type: str, payload: dict) -> dict:
        """Called only by the mailbox worker: the single writer to the socket."""
        response_id = self.next_response_id
        self.next_response_id += 1

        future = asyncio.get_running_loop().create_future()
        self.pending_requests[response_id] = future

        message = {
            "type": msg_type,
            "payload": payload,
            "responseId": response_id,
        }
        encoded = encode(message)

        try:
            async with self._send_lock:
                await self.websocket.send_bytes(encoded)
            return await asyncio.wait_for(future, timeout=self.RPC_TIMEOUT_SECONDS)
        finally:
            self.pending_requests.pop(response_id, None)

    def fail_pending(self, reason: str) -> None:
        """Fail all queued and outstanding RPC futures."""
        error = ConnectionError(reason)

        while True:
            try:
                command = self._mailbox.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not command.future.done():
                command.future.set_exception(error)
            self._mailbox.task_done()

        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(error)
        self.pending_requests.clear()

    async def close(self, code: int = 1000) -> None:
        """Revoke the connection: stop the actor and close the socket."""
        await self.stop()
        try:
            await self.websocket.close(code=code)
        except Exception:
            log.debug("connection.websocket_close_failed", exc_info=True)

    async def send_response(self, response_id: int, payload: dict):
        message = {
            "payload": payload,
            "responseId": response_id,
        }
        async with self._send_lock:
            await self.websocket.send_bytes(encode(message))

    async def handle_message(self, data: bytes):
        message = decode(data)

        if "type" not in message:
            response_id = message.get("responseId")
            future = (
                self.pending_requests.pop(response_id, None)
                if response_id is not None
                else None
            )
            if future is not None and not future.done():
                future.set_result(message.get("payload"))
            return

        msg_type = message.get("type")
        payload = message.get("payload", {})
        response_id = message.get("responseId")
        response = None

        if msg_type == "ready":
            response = {"type": "ok"}
            # `ready` may be retried by the plugin: start the handshake and
            # queue drain exactly once.
            if not self._ready_handled:
                self._ready_handled = True
                self.ready = True
                await self._publish_status()
                self._spawn(self._bootstrap(), name="puryfi-bootstrap")

        elif msg_type == "configurationChange":
            configuration = payload.get("configuration", self.configuration)
            self.configuration = configuration

        elif msg_type == "intentsGrant":
            granted_intents = payload.get("intents", [])
            required_intents = intents
            if all(intent in granted_intents for intent in required_intents):
                self.intents_granted_event.set()

        elif msg_type == "staticMediaScan":
            objects = payload.get("objects", [])
            await self._media_scans.record(
                self.session,
                objects,
                add_time=add_time_to_lock,
                create_log=create_custom_log,
            )

        if response_id is not None and response is not None:
            await self.send_response(response_id, response)

    async def _bootstrap(self) -> None:
        """Run the handshake and initial queue drain once, under a timeout."""
        try:
            initialized = await asyncio.wait_for(
                self.initialize_plugin(),
                timeout=self.HANDSHAKE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            log.warning(
                "connection.handshake_timeout",
                session_id=self.session.session_id,
            )
            await self.close(code=1011)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "connection.handshake_failed",
                session_id=self.session.session_id,
            )
            await self.close(code=1011)
            return

        if not initialized:
            log.warning(
                "connection.handshake_incomplete",
                session_id=self.session.session_id,
            )
            await self.close(code=1011)
            return

        try:
            await self.process_queued_messages(self.user_link_token)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "connection.queue_drain_failed",
                session_id=self.session.session_id,
            )

    async def initialize_plugin(self) -> bool:
        """Initialize the Puryfi plugin. Returns True only on full success."""
        try:
            # 1. Set Plugin Manifest
            res = await self.send_message("setPluginManifest", {"manifest": manifest})
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_manifest_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return False

            # 2. Set Plugin Configuration
            res = await self.send_message(
                "setPluginConfiguration", {"configuration": self.configuration}
            )
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_configuration_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return False

            # 3. Request Intents
            res = await self.send_message("getPluginIntents", {})
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_intents_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return False

            # 4. Request Intents
            granted_intents = res.get("intents", [])
            if all(intent in granted_intents for intent in intents):
                self.intents_granted_event.set()
            else:
                res = await self.send_message(
                    "requestPluginIntents", {"intents": intents}
                )
                if res.get("type", "") == "error":
                    log.warning(
                        "connection.plugin_intents_request_failed",
                        session_id=self.session.session_id,
                        error=res.get("message"),
                    )
                    return False
                # Wait for the client to grant intents through the
                # 'intentsGrant' message.
                await asyncio.wait_for(
                    self.intents_granted_event.wait(),
                    timeout=self.INTENTS_TIMEOUT_SECONDS,
                )

            # Get User State for username
            res = await self.send_message("getState", {"path": "user.username"})
            self.username = res.get("value")

            # Subscribe to static media scans
            res = await self.send_message("subscribeToStaticMediaScans", {})
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_scan_subscription_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return False

            return True

        except TimeoutError:
            log.warning(
                "connection.intents_timeout",
                session_id=self.session.session_id,
            )
            return False
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "connection.initialization_failed",
                session_id=self.session.session_id,
            )
            return False

    async def on_linked(self, session: LockSession) -> None:
        """Called by the outbound worker after a successful link transition."""
        self.session.has_linked_plugin = session.has_linked_plugin
        await self._publish_status()

    async def process_queued_messages(self, user_link_token: str) -> None:
        """Drain durable messages through the outbound worker."""
        await drain_queued_messages(
            connection=self,
            queue=self._queue,
            sessions=self._sessions,
            link_token=user_link_token,
            intents_timeout=self.INTENTS_TIMEOUT_SECONDS,
        )
