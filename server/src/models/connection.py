import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

import msgpack
from fastapi import WebSocket
from pymongo import ReturnDocument

from models.documents import UserLockConfiguration
from schemas import ChasterExtensionConfigSchema
from services.chaster import add_time_to_lock
from services.queue import fetch_queued_messages
from typings.puryfi_enums import PuryfiObjectLabel
from utils.chaster_api import create_custom_log

logger = logging.getLogger(__name__)

manifest = {
    "name": "Puryfier",
    "version": "0.3.0",
    "description": "Link Chaster with Puryfi",
    "author": "Sereti",
    "website": "https://paa.ge/sereti",
}

intents = [
    "readUserState", # read username
    "writeLockConfigurationState", # lock puryfi
    "writeEnabledState", # enable/disable puryfi
    "readMediaProcesses" # read media processes
]

# Labels that make a scanned media count as "censored" for the
# "add time when a media is censored" feature (REVIEW.md #11).
# Faces, hands, feet, eyes, ... are detected by Puryfi but are not
# censorable content, so they must not count.
CENSORABLE_LABELS = {
    PuryfiObjectLabel.Buttocks,
    PuryfiObjectLabel.FemaleBreast,
    PuryfiObjectLabel.FemaleGenitals,
    PuryfiObjectLabel.MaleGenitals,
    PuryfiObjectLabel.Anus,
    PuryfiObjectLabel.Nipple,
}


@dataclass
class _SendCommand:
    messages: list[tuple[str, dict]]
    future: asyncio.Future[list[dict]]


@dataclass
class _UpdateConfigCommand:
    config: ChasterExtensionConfigSchema
    future: asyncio.Future[None]


_MailboxCommand = _SendCommand | _UpdateConfigCommand


class Connection:
    def __init__(self, websocket: WebSocket, user_lock_config: UserLockConfiguration):
        self.websocket = websocket
        self.next_response_id = 0
        self.pending_requests = {}

        self.configuration: dict = {}

        self.username: str | None = None
        self.user_link_token: str = user_lock_config.link_token or ""
        self.user_lock_config: UserLockConfiguration = user_lock_config
        self.seen_censored_objects: int = (
            getattr(user_lock_config, "seen_censored_objects", 0) or 0
        )
        self.ready = False

        self.intents_granted_event = asyncio.Event()
        self._ready_handled = False
        self._tasks: set[asyncio.Task] = set()

        # One ordered mailbox per connection (REVIEW.md P1 #1): every
        # outbound command is queued here and sent by a single worker. This
        # serializes sends and keeps responseId correlation unambiguous.
        self._mailbox: asyncio.Queue[_MailboxCommand] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False

    # Seconds to wait for a Puryfi client response before failing the RPC
    # (REVIEW.md #5: an unanswered RPC must not hang forever).
    RPC_TIMEOUT_SECONDS = 15.0
    INTENTS_TIMEOUT_SECONDS = 30.0
    HANDSHAKE_TIMEOUT_SECONDS = 60.0

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
            logger.error("Connection task %s failed: %r", task.get_name(), exc)

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

    async def send_messages(
        self, messages: list[tuple[str, dict]]
    ) -> list[dict]:
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
                    self.user_lock_config.config = command.config
                    if not command.future.done():
                        command.future.set_result(None)
            except asyncio.CancelledError:
                # Do not propagate CancelledError to the webhook/queue caller:
                # a closing socket is a normal ConnectionError, not a reason to
                # cancel the durable webhook worker.
                if not command.future.done():
                    command.future.set_exception(ConnectionError("connection closed"))
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
        encoded = msgpack.packb(message)

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
            logger.debug("Failed to close Puryfi websocket", exc_info=True)

    async def send_response(self, response_id: int, payload: dict):
        message = {
            "payload": payload,
            "responseId": response_id,
        }
        encoded = msgpack.packb(message)
        async with self._send_lock:
            await self.websocket.send_bytes(encoded)

    async def _increment_censored_media(self) -> int:
        """Persist the counter per session and return its current value."""
        self.seen_censored_objects += 1
        config_id = getattr(self.user_lock_config, "id", None)
        if config_id is None:
            # Direct unit tests use a lightweight fake without a DB id.
            self.user_lock_config.seen_censored_objects = self.seen_censored_objects
            return self.seen_censored_objects

        document = await UserLockConfiguration.get_pymongo_collection().find_one_and_update(
            {"_id": config_id},
            {"$inc": {"seen_censored_objects": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if isinstance(document, dict) and isinstance(
            document.get("seen_censored_objects"), int
        ):
            self.seen_censored_objects = document["seen_censored_objects"]
        self.user_lock_config.seen_censored_objects = self.seen_censored_objects
        return self.seen_censored_objects

    async def _reset_censored_media(self) -> None:
        """Reset the persisted counter only after time was successfully added."""
        config_id = getattr(self.user_lock_config, "id", None)
        if config_id is not None:
            await UserLockConfiguration.get_pymongo_collection().update_one(
                {"_id": config_id},
                {"$set": {"seen_censored_objects": 0}},
            )
        self.seen_censored_objects = 0
        self.user_lock_config.seen_censored_objects = 0

    async def handle_message(self, data: bytes):
        message = msgpack.unpackb(data)
        
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
                # Imported here to avoid a module-level circular import.
                from models.connection_manager import manager

                await manager.publish_status(self)
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

            # One scan message == one scanned image. The feature counts
            # censored *images*, so a scan counts once, and only if it
            # contains at least one censorable label (REVIEW.md #11).
            has_censorable_content = any(
                obj.get("label") in CENSORABLE_LABELS for obj in objects
            )

            if has_censorable_content and self.user_lock_config.config.censorPicsConfig.enabled:
                count = await self._increment_censored_media()

                limit_reached = (
                    count
                    >= self.user_lock_config.config.censorPicsConfig.limit_count
                )
                if limit_reached and self.user_lock_config.session_id:
                    success = await add_time_to_lock(
                        self.user_lock_config.session_id,
                        self.user_lock_config.config.censorPicsConfig.added_duration,
                    )
                    # Keep the counter when add_time fails: the next scan must
                    # retry the penalty instead of losing it.
                    if success:
                        await self._reset_censored_media()
                        await create_custom_log(
                            self.user_lock_config.session_id,
                            role="extension",
                            title="%USER% added time!",
                            description=f"{self.user_lock_config.config.censorPicsConfig.added_duration} seconds added!",
                            icon="clock",
                            color="#ffffff",
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
            logger.warning(
                "Puryfi handshake timed out for session %r",
                self.user_lock_config.session_id,
            )
            await self.close(code=1011)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Puryfi handshake failed")
            await self.close(code=1011)
            return

        if not initialized:
            logger.warning(
                "Puryfi handshake did not complete for session %r",
                self.user_lock_config.session_id,
            )
            await self.close(code=1011)
            return

        try:
            await self.process_queued_messages(self.user_link_token)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Puryfi queue drain failed")

    async def initialize_plugin(self) -> bool:
        """Initialize the Puryfi plugin. Returns True only on full success."""
        try:
            # 1. Set Plugin Manifest
            res = await self.send_message("setPluginManifest", {"manifest": manifest})
            if res.get("type", "") == "error":
                print(f"Failed to set plugin manifest: {res.get('message')}")
                return False

            # 2. Set Plugin Configuration
            res = await self.send_message("setPluginConfiguration", {"configuration": self.configuration})
            if res.get("type", "") == "error":
                print(f"Failed to set plugin configuration: {res.get('message')}")
                return False

            # 3. Request Intents
            res = await self.send_message("getPluginIntents", {})
            if res.get("type", "") == "error":
                print(f"Failed to get plugin intents: {res.get('message')}")
                return False

            # 4. Request Intents
            granted_intents = res.get("intents", [])
            if all(intent in granted_intents for intent in intents):
                self.intents_granted_event.set()
            else:
                res = await self.send_message("requestPluginIntents", {"intents": intents})
                if res.get("type", "") == "error":
                    print(f"Failed to request plugin intents: {res.get('message')}")
                    return False
                # Wait for the client to grant intents through the 'intentsGrant' message
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
                print(f"Failed to subscribe to static media scans: {res.get('message')}")
                return False

            return True

        except TimeoutError:
            print("[Connection] Timed out waiting for plugin intents.")
            return False
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - one failed init must not kill the connection
            print(f"Initialization error: {type(e).__name__}")
            return False

    async def process_queued_messages(self, user_link_token: str) -> None:
        """
            Process queued messages for the connection.

            REVIEW.md #9: drain sequentially (ordering is semantic for a
            lock/unlock protocol), delete each message only after a successful
            send, and start draining only after intents are granted.
        """

        from models.connection_manager import manager
        from services.link import link_with_token

        # Queued messages (setState, enterLockPassword, ...) require intents;
        # wait until they are granted before draining.
        try:
            await asyncio.wait_for(
                self.intents_granted_event.wait(),
                timeout=self.INTENTS_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            print("[Queue] Intents were not granted in time; keeping queue.")
            return

        if not await link_with_token(user_link_token):
            return

        # The Puryfi handshake completed: tell the extension UI that the
        # plugin is now linked, without waiting for a page refresh.
        self.user_lock_config.has_linked_plugin = True
        await manager.publish_status(self)

        queued_messages = await fetch_queued_messages(user_link_token)

        for msg in queued_messages:
            print(f"[Queue] Sending queued message: {msg.msg_type}")
            res = await self.send_message(msg.msg_type, msg.payload)

            if isinstance(res, dict) and res.get("type") == "error":
                error_name = res.get("name")
                error_msg = res.get("message")
                print(f"[Queue Error] Failed to send '{msg.msg_type}': {error_name} - {error_msg}")

                if error_name == "missingPluginIntents":
                    # Keep the message queued for the next drain and re-request intents.
                    await self.send_message("requestPluginIntents", {"intents": intents})
                    return

                # Other errors: stop draining and keep this and the remaining
                # messages queued rather than dropping them out of order.
                return

            # Delivered: only now is it safe to remove it from the queue.
            await msg.delete()