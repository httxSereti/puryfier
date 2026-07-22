from utils.chaster_api import create_custom_log
from models.documents import UserLockConfiguration
from typings.puryfi_enums import PuryfiObjectLabel
import asyncio
import msgpack
from fastapi import WebSocket
from services.chaster import add_time_to_lock

from services.queue import fetch_queued_messages, queue_message

manifest = {
    "name": "Puryfier",
    "version": "0.2.0",
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

class Connection:
    def __init__(self, websocket: WebSocket, user_lock_config: UserLockConfiguration):
        self.websocket = websocket
        self.next_response_id = 0
        self.pending_requests = {}

        self.configuration: dict = {}

        self.username: str | None = None
        self.user_link_token: str = user_lock_config.link_token or ""
        self.user_lock_config: UserLockConfiguration = user_lock_config
        self.seen_censored_objects: int = 0

        self.intents_granted_event = asyncio.Event()

    # Seconds to wait for a Puryfi client response before failing the RPC
    # (REVIEW.md #5: an unanswered RPC must not hang forever).
    RPC_TIMEOUT_SECONDS = 15.0

    async def send_message(self, msg_type: str, payload: dict) -> dict:
        response_id = self.next_response_id
        self.next_response_id += 1

        future = asyncio.get_event_loop().create_future()
        self.pending_requests[response_id] = future

        message = {
            "type": msg_type,
            "payload": payload,
            "responseId": response_id
        }
        encoded = msgpack.packb(message)
        await self.websocket.send_bytes(encoded)

        try:
            return await asyncio.wait_for(future, timeout=self.RPC_TIMEOUT_SECONDS)
        finally:
            self.pending_requests.pop(response_id, None)

    def fail_pending(self, reason: str) -> None:
        """Fail all outstanding RPC futures, e.g. when the connection drops."""
        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self.pending_requests.clear()

    async def send_response(self, response_id: int, payload: dict):
        message = {
            "payload": payload,
            "responseId": response_id
        }
        encoded = msgpack.packb(message)
        await self.websocket.send_bytes(encoded)

    async def handle_message(self, data: bytes):
        message = msgpack.unpackb(data)
        
        if "type" not in message:
            response_id = message.get("responseId")
            if response_id is not None and response_id in self.pending_requests:
                self.pending_requests[response_id].set_result(message.get("payload"))
                del self.pending_requests[response_id]
            return
        
        msg_type = message.get("type")
        payload = message.get("payload", {})
        response_id = message.get("responseId")
        response = None

        if msg_type == "ready":
            response = {"type": "ok"}
            # Start initialization process in background
            asyncio.create_task(self.initialize_plugin())
            asyncio.create_task(self.process_queued_messages(self.user_link_token))
            
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
                self.seen_censored_objects += 1

                if self.seen_censored_objects >= self.user_lock_config.config.censorPicsConfig.limit_count:
                    self.seen_censored_objects = 0

                    if self.user_lock_config.session_id:
                        success = await add_time_to_lock(self.user_lock_config.session_id, self.user_lock_config.config.censorPicsConfig.added_duration)
                        if success:
                            await create_custom_log(
                                self.user_lock_config.session_id,
                                role="extension",
                                title="%USER% added time!",
                                description=f"{self.user_lock_config.config.censorPicsConfig.added_duration} seconds added!",
                                icon="clock",
                                color="#ffffff"
                            )

        if response_id is not None and response is not None:
            await self.send_response(response_id, response)

    async def initialize_plugin(self):
        """
            Initialize Plugin inside Puryfi
        """
        
        try:
            # 1. Set Plugin Manifest
            res = await self.send_message("setPluginManifest", {"manifest": manifest})
            if res.get("type", "") == "error":
                print(f"Failed to set plugin manifest: {res.get('message')}")
                return

            # 2. Set Plugin Configuration
            res = await self.send_message("setPluginConfiguration", {"configuration": self.configuration})
            if res.get("type", "") == "error":
                print(f"Failed to set plugin configuration: {res.get('message')}")
                return

            # 3. Request Intents
            res = await self.send_message("getPluginIntents", {})
            if res.get("type", "") == "error":
                print(f"Failed to get plugin intents: {res.get('message')}")
                return
                
            # 4. Request Intents
            granted_intents = res.get("intents", [])
            if all(intent in granted_intents for intent in intents):
                self.intents_granted_event.set()
            else:
                res = await self.send_message("requestPluginIntents", {"intents": intents})
                if res.get("type", "") == "error":
                    print(f"Failed to request plugin intents: {res.get('message')}")
                    return
                # Wait for the client to grant intents through the 'intentsGrant' message
                await self.intents_granted_event.wait()
                
            # Get User State for username
            res = await self.send_message("getState", {"path": "user.username"})
            self.username = res.get("value")
            
            # Subscribe to static media scans
            res = await self.send_message("subscribeToStaticMediaScans", {})
            if res.get("type", "") == "error":
                print(f"Failed to subscribe to static media scans: {res.get('message')}")

        except Exception as e:
            print(f"Initialization error: {e}")

    async def process_queued_messages(self, user_link_token: str) -> None:
        """
            Process queued messages for the connection.

            REVIEW.md #9: drain sequentially (ordering is semantic for a
            lock/unlock protocol), delete each message only after a successful
            send, and start draining only after intents are granted.
        """

        from services.link import link_with_token

        if not await link_with_token(user_link_token):
            return

        # Queued messages (setState, enterLockPassword, ...) require intents;
        # wait until they are granted before draining.
        await self.intents_granted_event.wait()

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