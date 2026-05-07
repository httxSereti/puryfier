import asyncio
import msgpack
from fastapi import WebSocket
from utils.chaster_api import addDurationToLock
from services.queue import fetch_and_delete_queued_messages

manifest = {
    "name": "Puryfi-Chaster-Linker",
    "version": "1.0.0",
    "description": "Link Puryfi with your Chaster lock",
    "author": "Sereti",
    "website": "https://paa.ge/sereti",
}

intents = [
    "readUserState", # read username
    "writeLockConfigurationState", # lock puryfi
    "writeEnabledState", # enable/disable puryfi
]

class Connection:
    def __init__(self, websocket: WebSocket, user_link_token: str):
        self.websocket = websocket
        self.next_response_id = 0
        self.pending_requests = {}

        self.username: str | None = None
        self.user_link_token: str = user_link_token

        self.configuration: dict = {}
        self.intents_granted_event = asyncio.Event()

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
        
        return await future

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
            if not all(intent in granted_intents for intent in intents):
                res = await self.send_message("requestPluginIntents", {"intents": intents})
                if res.get("type", "") == "error":
                    print(f"Failed to request plugin intents: {res.get('message')}")
                    return
                # Wait for the client to grant intents through the 'intentsGrant' message
                await self.intents_granted_event.wait()
                
            # Get User State for username
            res = await self.send_message("getState", {"path": "user.username"})
            self.username = res.get("value")

        except Exception as e:
            print(f"Initialization error: {e}")

    async def process_queued_messages(self, user_link_token: str) -> None:
        """
            Process queued messages for the connection
        """
        
        from services.link import link_with_token
        
        if await link_with_token(user_link_token):
            queued_messages = await fetch_and_delete_queued_messages(user_link_token)
            
            """
                Send queued messages to Puryfi plugin
                Handle errors and requeue if necessary
            """
            async def process_queue_msg(msg_type, payload):
                res = await self.send_message(msg_type, payload)
                if isinstance(res, dict) and res.get("type") == "error":
                    error_name = res.get("name")
                    error_msg = res.get("message")
                    print(f"[Queue Error] Failed to send '{msg_type}': {error_name} - {error_msg}")
                    
                    if error_name == "missingPluginIntents":
                        print("[Queue] Requeuing message due to missing intents")
                        from services.queue import queue_message
                        await queue_message(user_link_token, msg_type, payload)
                        # Optionally request intents again
                        await self.send_message("requestPluginIntents", {"intents": intents})

            for msg in queued_messages:
                print(f"[Queue] Sending queued message: {msg['msg_type']}")
                asyncio.create_task(process_queue_msg(msg["msg_type"], msg["payload"]))