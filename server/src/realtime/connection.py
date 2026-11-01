"""One supervised actor per Puryfi WebSocket connection."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from fastapi import WebSocket

from domain.automation_models import (
    EVENT_PURYFI_CONNECTION_DISCONNECTED,
    EVENT_PURYFI_CONNECTION_READY,
    EVENT_PURYFI_STATE_CHANGED,
    EVENT_PURYFI_USER_CHANGED,
    PURYFI_LOCK_INTENTS,
)
from domain.automations.engine import AutomationEngine
from domain.entities import (
    ChasterExtensionConfigSchema,
    LockSession,
    PuryfiSupportTierSchema,
)
from domain.ports import LockSessionRepository, MediaScanSink, MessageQueue
from infra.logging import get_logger
from infra.queue import MongoMessageQueue
from infra.repositories import MongoLockSessionRepository
from realtime.protocol import (
    decode,
    encode,
    intents,
    manifest,
    optional_intents,
)
from workers.outbound import drain_queued_messages

log = get_logger(__name__)

# Plugin API compatibility window advertised by the PuryFi SDK:
# ``[1.0.0, 2.0.0)`` (minApiVersion / maxApiVersion in connection.ts).
MIN_API_VERSION = (1, 0, 0)
MAX_API_VERSION = (2, 0, 0)
_SUPPORTED_API_VERSIONS = "[1.0.0, 2.0.0)"


def _parse_api_version(value: object) -> tuple[int, int, int] | None:
    """Parse an API version with the same three-part shape as the SDK."""
    if not isinstance(value, str):
        return None

    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


__all__ = [
    "Connection",
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
        media_scans: MediaScanSink | None = None,
        automation_engine: AutomationEngine | None = None,
    ):
        self.websocket = websocket
        self.session: LockSession = user_lock_config
        self.next_response_id = 0
        self.pending_requests = {}

        self.configuration: dict = {}

        self.username: str | None = None
        self.support_tier: PuryfiSupportTierSchema | None = None
        self.ready = False
        # Metadata advertised by PuryFi in `ready`, kept for diagnostics.
        self.puryfi_version: str | None = None
        self.api_version: str | None = None
        self.instance_id: str | None = None
        # Live PuryFi state shown in the extension UI (optional permissions).
        self.granted_intents: set[str] = set()
        self.puryfi_enabled: bool | None = None
        self.puryfi_has_lock: bool | None = None

        self.intents_granted_event = asyncio.Event()
        self._ready_handled = False
        self._tasks: set[asyncio.Task] = set()
        # Intent-gated setup (profile + media scan subscription) runs once,
        # either at the end of the bootstrap or when the grant arrives later.
        self._handshake_completed = False
        self._intents_setup_lock = asyncio.Lock()
        self._intents_setup_done = False

        self._sessions = sessions or MongoLockSessionRepository()
        self._queue = queue or MongoMessageQueue()
        # A process-wide batcher is injected by the composition root. Direct
        # unit tests that do not care about media scans may omit it.
        self._media_scans = media_scans
        self._automation_engine = automation_engine
        self._status_publisher: StatusPublisher | None = None

        # One ordered mailbox per connection: every outbound command is queued
        # here and sent by a single worker. This serializes sends and keeps
        # responseId correlation unambiguous.
        self._mailbox: asyncio.Queue[_MailboxCommand] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        # Serialize queue drains: the bootstrap, the `intentsGrant` handler and
        # webhook-triggered flushes must never deliver the same command twice.
        self._drain_lock = asyncio.Lock()
        # Serialize profile/state snapshots: the handshake, optional intent
        # grants and browser watchers can all request a refresh.
        self._snapshot_lock = asyncio.Lock()
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
    def intents_granted(self) -> bool:
        return self.intents_granted_event.is_set()

    @property
    def can_send_protected(self) -> bool:
        """True once PuryFi completed the handshake and granted our intents."""
        return not self._closed and self.ready and self.intents_granted

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

    def _automation_context(self) -> dict[str, object]:
        """Snapshot the state automation conditions can inspect."""
        return {
            "chaster_frozen": bool(
                getattr(self.session, "chaster_frozen", False)
            ),
            "puryfi_enabled": self.puryfi_enabled,
            "puryfi_has_lock": self.puryfi_has_lock,
        }

    def _record_automation_event(
        self,
        event_type: str,
        payload: dict | None = None,
    ) -> None:
        """Feed a PuryFi protocol event to the rule engine without blocking.

        The engine only schedules work when the session has an enabled rule
        for this event. Profile/state updates themselves stay synchronous.
        """
        engine = self._automation_engine
        if engine is None:
            return
        if (
            not getattr(self.session, "automation_mode", False)
            and not engine.has_rules(self.session.session_id)
        ):
            return

        try:
            engine.record_event_nowait(
                self.session,
                event_type=event_type,
                payload=payload or {},
                context=self._automation_context(),
            )
        except Exception:
            log.exception(
                "connection.automation_event_failed",
                session_id=getattr(self.session, "session_id", None),
                event_type=event_type,
            )

    def notify_disconnected(self, *, was_ready: bool | None = None) -> None:
        """Emit the disconnect event for a genuine PuryFi socket closure."""
        if not (self.ready if was_ready is None else was_ready):
            return
        if getattr(self.session, "chaster_frozen", False):
            log.warning(
                "connection.disconnected_while_frozen",
                session_id=getattr(self.session, "session_id", None),
                puryfi_version=self.puryfi_version,
            )
        self._record_automation_event(
            EVENT_PURYFI_CONNECTION_DISCONNECTED,
            {
                "puryfi_version": self.puryfi_version,
                "api_version": self.api_version,
                "instance_id": self.instance_id,
            },
        )

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
        start_bootstrap = False

        if msg_type == "ready":
            response = self._accept_ready(payload)
            # `ready` may be retried by the plugin: start the handshake and
            # queue drain exactly once, and only for a compatible API version.
            if response["type"] == "ok" and not self._ready_handled:
                self._ready_handled = True
                log.info(
                    "connection.ready",
                    session_id=self.session.session_id,
                    puryfi_version=self.puryfi_version,
                    api_version=self.api_version,
                    instance_id=self.instance_id,
                )
                await self._publish_status()
                self._record_automation_event(
                    EVENT_PURYFI_CONNECTION_READY,
                    {
                        "puryfi_version": self.puryfi_version,
                        "api_version": self.api_version,
                        "instance_id": self.instance_id,
                    },
                )
                start_bootstrap = True

        elif msg_type == "configurationChange":
            configuration = payload.get("configuration", self.configuration)
            self.configuration = configuration

        elif msg_type == "intentsGrant":
            granted = set(payload.get("intents", []))
            previous = self.granted_intents
            removed = sorted(previous - granted)
            self.granted_intents = granted

            revoked_lock_intents = sorted(
                set(PURYFI_LOCK_INTENTS) & set(removed)
            )
            if revoked_lock_intents:
                log.warning(
                    "connection.lock_intents_revoked",
                    session_id=self.session.session_id,
                    removed_intents=revoked_lock_intents,
                )

            newly_optional = {
                intent
                for intent in optional_intents
                if intent in granted and intent not in previous
            }
            if newly_optional and self.ready and self._handshake_completed:
                self._spawn(
                    self.refresh_puryfi_state(),
                    name="puryfi-optional-state-refresh",
                )

            all_required_granted = all(
                intent in granted for intent in intents
            )
            if all_required_granted:
                newly_granted = not self.intents_granted_event.is_set()
                self.intents_granted_event.set()
                # Commands queued while intents were missing must not wait for
                # a reconnect: finish the intent-gated setup, then drain them
                # as soon as the grant arrives.
                if (
                    newly_granted
                    and self.ready
                    and self._handshake_completed
                ):
                    self._spawn(
                        self._on_intents_granted(),
                        name="puryfi-intents-drain",
                    )
            else:
                # Permissions can be revoked after the handshake. Protected
                # commands must stay in the durable queue until they return.
                self.intents_granted_event.clear()

        elif msg_type == "stateChange":
            # Keep the cached profile and PuryFi state in sync. These handlers
            # only touch memory; persistence runs in a supervised task.
            if self._handle_profile_state_change(payload):
                self._record_automation_event(
                    EVENT_PURYFI_USER_CHANGED,
                    payload,
                )
            if self._handle_puryfi_state_change(payload):
                self._record_automation_event(
                    EVENT_PURYFI_STATE_CHANGED,
                    {
                        "path": payload.get("path"),
                        "puryfi_enabled": self.puryfi_enabled,
                        "puryfi_has_lock": self.puryfi_has_lock,
                    },
                )

        elif msg_type == "staticMediaScan":
            # Never do I/O here: PuryFi can emit dozens of scans per second and
            # this read loop also receives the responses of pending RPCs. The
            # automation engine and the legacy batcher only update in-memory
            # counters.
            objects = payload.get("objects", [])
            handled = False
            if self._automation_engine is not None:
                try:
                    handled = self._automation_engine.record_nowait(
                        self.session,
                        objects,
                    )
                except Exception:
                    log.exception(
                        "connection.automation_scan_failed",
                        session_id=getattr(self.session, "session_id", None),
                    )
                    handled = bool(self.session.automation_mode)

            if not handled and self._media_scans is not None:
                try:
                    self._media_scans.record_nowait(
                        self.session,
                        objects,
                    )
                except Exception:
                    log.exception(
                        "connection.media_scan_enqueue_failed",
                        session_id=getattr(self.session, "session_id", None),
                    )

        if response_id is not None and response is not None:
            await self.send_response(response_id, response)

        # Only now may the handshake RPCs reach PuryFi: the runtime ignores
        # plugin frames until it received this acknowledgement.
        if start_bootstrap:
            self._spawn(self._bootstrap(), name="puryfi-bootstrap")

    def _accept_ready(self, payload: dict) -> dict:
        """Record `ready` metadata and validate the offered plugin API version.

        The response follows the PuryFi runtime (and SDK) contract: errors use
        the ``name`` key, unlike regular RPC error payloads.
        """
        version = payload.get("version")
        api_version = payload.get("apiVersion")
        instance_id = payload.get("instanceId")

        if isinstance(version, str):
            self.puryfi_version = version
        if isinstance(api_version, str):
            self.api_version = api_version
        if isinstance(instance_id, str):
            self.instance_id = instance_id

        parsed = _parse_api_version(api_version)
        if parsed is None or not MIN_API_VERSION <= parsed < MAX_API_VERSION:
            log.warning(
                "connection.incompatible_api_version",
                session_id=self.session.session_id,
                puryfi_version=version,
                api_version=api_version,
                supported_api_versions=_SUPPORTED_API_VERSIONS,
                instance_id=instance_id,
            )
            return {
                "type": "error",
                "name": "incompatibleApiVersion",
                "message": (
                    "Puryfier requires a PuryFi plugin API version in "
                    f"{_SUPPORTED_API_VERSIONS}, got {api_version!r}"
                ),
            }

        self.ready = True
        return {"type": "ok"}

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

        # Never block the handshake on a pending intents approval: the queue
        # is drained by `intentsGrant` if the user grants them later.
        await self._on_intents_granted()

    async def initialize_plugin(self) -> bool:
        """Send the mandatory handshake messages.

        Intents may still be pending when this returns True: PuryFi requires
        the user to approve them, possibly long after the connection opened.
        The grant arrives as an ``intentsGrant`` event, which triggers the
        intent-gated setup and queue drain. Returns False only when a
        mandatory RPC failed.
        """
        step = "setPluginManifest"
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
            step = "setPluginConfiguration"
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

            # 3. Read the intents already granted in the past.
            step = "getPluginIntents"
            res = await self.send_message("getPluginIntents", {})
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_intents_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return False

            # 4. Request the missing intents. PuryFi only marks them pending;
            # the user (or the runtime) grants them with `intentsGrant`.
            granted_intents = set(res.get("intents", []))
            self.granted_intents = granted_intents
            missing_intents = [
                intent for intent in intents if intent not in granted_intents
            ]
            missing_optional = [
                intent
                for intent in optional_intents
                if intent not in granted_intents
            ]
            if missing_intents:
                step = "requestPluginIntents"
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
                log.info(
                    "connection.intents_pending",
                    session_id=self.session.session_id,
                    missing_intents=missing_intents,
                    optional_intents=missing_optional,
                )
                await self._request_optional_intents(missing_optional)
            elif missing_optional:
                # Optional permissions only power the live state display: the
                # handshake must not wait for the user to approve them.
                await self._request_optional_intents(missing_optional)
                self.intents_granted_event.set()
            else:
                self.intents_granted_event.set()

            self._handshake_completed = True
            if self.intents_granted:
                step = "subscribeToStaticMediaScans"
                await self._complete_intents_setup()
            return True

        except TimeoutError:
            log.warning(
                "connection.handshake_rpc_timeout",
                session_id=self.session.session_id,
                step=step,
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

    async def _request_optional_intents(
        self, missing_optional: list[str]
    ) -> None:
        """Ask for optional state permissions without failing the handshake."""
        if not missing_optional:
            return

        try:
            res = await self.send_message(
                "requestPluginIntents", {"intents": optional_intents}
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning(
                "connection.optional_intents_request_failed",
                session_id=self.session.session_id,
                exc_info=True,
            )
            return

        if isinstance(res, dict) and res.get("type") == "error":
            log.warning(
                "connection.optional_intents_request_rejected",
                session_id=self.session.session_id,
                error=res.get("message"),
            )
            return

        log.info(
            "connection.optional_intents_pending",
            session_id=self.session.session_id,
            optional_intents=missing_optional,
        )

    async def _on_intents_granted(self) -> None:
        """Finish intent-gated setup, then deliver the queued commands."""
        try:
            await self._complete_intents_setup()
            await self.flush_queue()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "connection.intents_setup_failed",
                session_id=self.session.session_id,
            )

    async def _complete_intents_setup(self) -> None:
        """Run the RPCs that require intents, exactly once per connection."""
        if not self._handshake_completed or not self.intents_granted:
            return

        async with self._intents_setup_lock:
            if (
                self._intents_setup_done
                or not self._handshake_completed
                or not self.intents_granted
            ):
                return

            # Read the PuryFi profile/state used by the session UI. This is
            # diagnostic metadata: a failure must not fail the handshake.
            await self.refresh_snapshot(publish=False)
            self._schedule_profile_retry()

            # Subscribe to static media scans
            res = await self.send_message("subscribeToStaticMediaScans", {})
            if res.get("type", "") == "error":
                log.warning(
                    "connection.plugin_scan_subscription_failed",
                    session_id=self.session.session_id,
                    error=res.get("message"),
                )
                return

            self._intents_setup_done = True

    async def _read_state_result(
        self, path: str
    ) -> tuple[bool, object | None]:
        """Read one PuryFi state path without making it handshake-critical.

        Returns ``(True, value)`` for a successful response, including a
        legitimate ``null`` value, and ``(False, None)`` on transport or
        runtime errors.
        """
        try:
            res = await self.send_message("getState", {"path": path})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning(
                "connection.profile_state_failed",
                session_id=self.session.session_id,
                path=path,
                exc_info=True,
            )
            return False, None

        if not isinstance(res, dict):
            return False, None
        if res.get("type") == "error":
            log.debug(
                "connection.profile_state_rejected",
                session_id=self.session.session_id,
                path=path,
                error=res.get("message"),
            )
            return False, None
        return True, res.get("value")

    async def _read_state(self, path: str) -> object | None:
        ok, value = await self._read_state_result(path)
        return value if ok else None

    def _apply_username(
        self, value: object, updates: dict[str, object]
    ) -> None:
        if (
            isinstance(value, str)
            and value
            and value != getattr(self.session, "puryfi_username", None)
        ):
            self.username = value
            self.session.puryfi_username = value
            updates["puryfi_username"] = value

    def _apply_support_tier(
        self, value: object, updates: dict[str, object]
    ) -> None:
        if not isinstance(value, dict):
            return

        try:
            support_tier = PuryfiSupportTierSchema(**value)
        except (TypeError, ValueError):
            log.warning(
                "connection.profile_support_tier_invalid",
                session_id=self.session.session_id,
            )
            return

        if support_tier != getattr(self.session, "puryfi_support_tier", None):
            self.support_tier = support_tier
            self.session.puryfi_support_tier = support_tier
            updates["puryfi_support_tier"] = support_tier

    async def _load_profile(self) -> bool:
        """Read and persist the PuryFi user profile shown in the extension UI.

        The root ``user`` path is read first because PuryFi exposes it as
        ``null`` while the account is unavailable; the leaf paths are only a
        fallback for older runtimes.
        """
        updates: dict[str, object] = {}

        profile = await self._read_state("user")
        if isinstance(profile, dict):
            self._apply_username(profile.get("username"), updates)
            self._apply_support_tier(profile.get("supportTier"), updates)
        else:
            self._apply_username(
                await self._read_state("user.username"), updates
            )
            self._apply_support_tier(
                await self._read_state("user.supportTier"), updates
            )

        if updates:
            await self._persist_profile(updates)
        return bool(updates)

    async def _subscribe_to_state(self) -> None:
        """Subscribe to every state path needed by the session UI.

        Subscribing to ``user`` (instead of ``user.username``) still works
        when PuryFi temporarily exposes ``user`` as ``null``.
        """
        paths = ["user"]
        if "readEnabledState" in self.granted_intents:
            paths.append("enabled")
        if "readLockConfigurationState" in self.granted_intents:
            paths.append("lockConfiguration")

        try:
            responses = await self.send_messages(
                [("subscribeToState", {"path": path}) for path in paths]
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning(
                "connection.state_subscription_failed",
                session_id=self.session.session_id,
                paths=paths,
                exc_info=True,
            )
            return

        for path, res in zip(paths, responses, strict=False):
            if isinstance(res, dict) and res.get("type") == "error":
                log.warning(
                    "connection.state_subscription_rejected",
                    session_id=self.session.session_id,
                    path=path,
                    error=res.get("message"),
                )

    async def _load_puryfi_state(self) -> bool:
        """Read the optional enabled/lock state without keeping any secret."""
        changed = False

        if "readEnabledState" in self.granted_intents:
            ok, value = await self._read_state_result("enabled")
            if ok and isinstance(value, bool) and value != self.puryfi_enabled:
                self.puryfi_enabled = value
                changed = True

        if "readLockConfigurationState" in self.granted_intents:
            ok, value = await self._read_state_result("lockConfiguration")
            if ok:
                has_lock = isinstance(value, dict)
                if has_lock != self.puryfi_has_lock:
                    self.puryfi_has_lock = has_lock
                    changed = True

        return changed

    async def refresh_puryfi_state(self) -> None:
        """Refresh only the optional PuryFi state (permission-gated)."""
        if not self.can_send_protected:
            return
        async with self._snapshot_lock:
            if not self.can_send_protected:
                return
            await self._subscribe_to_state()
            if await self._load_puryfi_state():
                await self._publish_status()

    async def refresh_snapshot(self, *, publish: bool = True) -> None:
        """Re-read the profile and optional state from a live PuryFi client."""
        if not self.can_send_protected:
            return
        async with self._snapshot_lock:
            if not self.can_send_protected:
                return
            await self._subscribe_to_state()
            profile_changed = await self._load_profile()
            state_changed = await self._load_puryfi_state()
            if publish and (profile_changed or state_changed):
                await self._publish_status()

    def request_snapshot_refresh(self) -> None:
        """Schedule a snapshot refresh from a browser watcher (best effort)."""
        if self.can_send_protected:
            self._spawn(
                self.refresh_snapshot(),
                name="puryfi-snapshot-refresh",
            )

    async def _retry_profile_until_available(self) -> None:
        """Retry a few times while PuryFi is still loading the account."""
        for delay in (2.0, 8.0, 30.0):
            await asyncio.sleep(delay)
            if (
                self._closed
                or not self.can_send_protected
                or getattr(self.session, "puryfi_username", None)
            ):
                return
            await self.refresh_snapshot()

    def _schedule_profile_retry(self) -> None:
        if getattr(self.session, "puryfi_username", None):
            return
        self._spawn(
            self._retry_profile_until_available(),
            name="puryfi-profile-retry",
        )

    def _handle_puryfi_state_change(self, payload: dict) -> bool:
        """Update the cached enabled/lock state reported by PuryFi.

        Returns True when the cached value actually changed, so the same
        protocol message can feed the automation engine.
        """
        path = payload.get("path")
        value = payload.get("value")
        changed = False

        if path == "enabled" and isinstance(value, bool):
            if value != self.puryfi_enabled:
                self.puryfi_enabled = value
                changed = True
                if (
                    not value
                    and getattr(self.session, "chaster_frozen", False)
                ):
                    log.warning(
                        "connection.puryfi_disabled_while_frozen",
                        session_id=getattr(
                            self.session, "session_id", None
                        ),
                    )
        elif path == "lockConfiguration":
            has_lock = isinstance(value, dict)
            if has_lock != self.puryfi_has_lock:
                self.puryfi_has_lock = has_lock
                changed = True

        if changed:
            self._spawn(self._publish_status(), name="puryfi-state-publish")
        return changed

    def _handle_profile_state_change(self, payload: dict) -> bool:
        """Update the cached profile when PuryFi reports a ``user`` change."""
        path = payload.get("path")
        value = payload.get("value")
        updates: dict[str, object] = {}

        if path == "user" and isinstance(value, dict):
            self._apply_username(value.get("username"), updates)
            self._apply_support_tier(value.get("supportTier"), updates)
        elif path == "user.username":
            self._apply_username(value, updates)
        elif path == "user.supportTier":
            self._apply_support_tier(value, updates)

        if updates:
            self._spawn(
                self._persist_profile_and_publish(updates),
                name="puryfi-profile-sync",
            )
            return True
        return False

    async def _persist_profile_and_publish(
        self, updates: dict[str, object]
    ) -> None:
        await self._persist_profile(updates)
        await self._publish_status()

    async def _persist_profile(self, updates: dict[str, object]) -> None:
        """Best-effort persistence: the profile is not needed to lock PuryFi."""
        if not self.session.session_id:
            return

        update = getattr(self._sessions, "update", None)
        if update is None:
            return

        try:
            await update(self.session.session_id, **updates)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(
                "connection.profile_persist_failed",
                session_id=self.session.session_id,
            )

    async def on_linked(self, session: LockSession) -> None:
        """Called by the outbound worker after a successful link transition."""
        self.session.has_linked_plugin = session.has_linked_plugin
        await self._publish_status()

    async def flush_queue(self) -> bool:
        """Deliver durable commands if the plugin is ready and intents granted.

        Never waits for readiness: when the plugin is not ready yet, the
        commands stay queued and the bootstrap (or the next ``intentsGrant``)
        drains them. Returns True only when every queued message was delivered.
        """
        if not self.can_send_protected:
            return False

        async with self._drain_lock:
            # Readiness may have changed while waiting for the lock (e.g. the
            # socket closed): re-check before touching the queue.
            if not self.can_send_protected:
                return False
            return await drain_queued_messages(
                connection=self,
                queue=self._queue,
                sessions=self._sessions,
                link_token=self.user_link_token,
                intents_timeout=self.INTENTS_TIMEOUT_SECONDS,
                wait_for_intents=False,
            )

    async def process_queued_messages(
        self, user_link_token: str, *, wait_for_intents: bool = True
    ) -> bool:
        """Drain durable messages through the outbound worker."""
        async with self._drain_lock:
            return await drain_queued_messages(
                connection=self,
                queue=self._queue,
                sessions=self._sessions,
                link_token=user_link_token,
                intents_timeout=self.INTENTS_TIMEOUT_SECONDS,
                wait_for_intents=wait_for_intents,
            )
