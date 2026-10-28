import httpx
from beanie.exceptions import CollectionWasNotInitialized
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pymongo.errors import PyMongoError

from models.connection import Connection
from models.connection_manager import manager
from models.documents import UserLockConfiguration
from models.session_watchers import watchers
from utils import chaster_api
from utils.redaction import token_fingerprint

router = APIRouter(prefix="/ws")


async def watch_session(
    websocket: WebSocket,
    session_id: str,
    lock_config: UserLockConfiguration,
) -> None:
    """Stream the Puryfi connection status of a session to a browser socket."""
    await websocket.accept()
    watchers.add(session_id, websocket)

    try:
        # Always send the current state first: the page may have been opened
        # while Puryfi was already connected.
        await websocket.send_json(manager.status_for_lock_config(lock_config))

        while True:
            # The page only listens. Receiving lets us notice the disconnect
            # promptly (and tolerates app-level keepalives).
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        watchers.remove(session_id, websocket)


@router.websocket("/session/{main_token}")
async def session_status_endpoint(websocket: WebSocket, main_token: str):
    """Realtime Puryfi status for the extension main page."""
    try:
        data = await chaster_api.get_session_auth(main_token)
    except HTTPException as e:
        print(f"[WS-Realtime] Chaster rejected the session token: {e.status_code}")
        await websocket.close(code=4004)
        return
    except Exception as e:  # noqa: BLE001 - never leave the browser socket hanging
        print(
            "[WS-Realtime] Could not authenticate the session token "
            f"{token_fingerprint(main_token)}: {type(e).__name__}"
        )
        await websocket.close(code=1011)
        return

    if not isinstance(data, dict):
        await websocket.close(code=4004)
        return

    session = data.get("session")
    session_id = session.get("sessionId") if isinstance(session, dict) else None
    if not session_id:
        await websocket.close(code=4004)
        return

    try:
        lock_config = await UserLockConfiguration.find_one(
            UserLockConfiguration.session_id == session_id
        )
    except (CollectionWasNotInitialized, PyMongoError) as e:
        print(f"[WS-Realtime] Error fetching user lock configuration: {e}")
        await websocket.close(code=1011)
        return

    if lock_config is None:
        await websocket.close(code=4004)
        return

    await watch_session(websocket, session_id, lock_config)


@router.websocket("/configuration/{configuration_token}")
async def configuration_status_endpoint(websocket: WebSocket, configuration_token: str):
    """Realtime Puryfi status for the extension configuration page."""
    try:
        response = await chaster_api.chaster_client.get(
            f"/api/extensions/configurations/{configuration_token}"
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        print(f"[WS-Realtime] Chaster rejected the configuration token: {e.response.status_code}")
        await websocket.close(code=4004)
        return
    except httpx.HTTPError as e:
        print(
            "[WS-Realtime] Could not fetch the configuration "
            f"{token_fingerprint(configuration_token)}: {type(e).__name__}"
        )
        await websocket.close(code=1011)
        return
    except (TypeError, ValueError) as e:
        print(f"[WS-Realtime] Invalid configuration response: {type(e).__name__}")
        await websocket.close(code=1011)
        return

    if not isinstance(data, dict):
        await websocket.close(code=4004)
        return

    session_id = data.get("sessionId")
    if not session_id:
        await websocket.close(code=4004)
        return

    try:
        lock_config = await UserLockConfiguration.find_one(
            UserLockConfiguration.session_id == session_id
        )
    except (CollectionWasNotInitialized, PyMongoError) as e:
        print(f"[WS-Realtime] Error fetching user lock configuration: {e}")
        await websocket.close(code=1011)
        return

    if lock_config is None:
        await websocket.close(code=4004)
        return

    await watch_session(websocket, session_id, lock_config)


@router.websocket("/{user_link_token}")
async def websocket_endpoint(websocket: WebSocket, user_link_token: str):
    """
        Handle WebSocket connections from Puryfi plugin through WebSocket.
        user_link_token: The user link token used to identify the user.
    """
    # Validate the token BEFORE accepting the connection (REVIEW.md #6).
    try:
        user_lock_config = await UserLockConfiguration.find_one(
            UserLockConfiguration.link_token == user_link_token
        )
    except (CollectionWasNotInitialized, PyMongoError) as e:
        print(f"[WS-Puryfi] Error fetching user lock configuration: {e}")
        await websocket.close(code=1011)
        return

    if user_lock_config is None:
        print(
            "[WS-Puryfi] User lock configuration not found for token "
            f"{token_fingerprint(user_link_token)}"
        )
        await websocket.close(code=4004)
        return

    await websocket.accept()

    # connect WebSocket
    connection = Connection(websocket, user_lock_config)
    await manager.add(connection, user_link_token)

    print(
        "[WS-Puryfi] Connection established for token "
        f"{token_fingerprint(user_link_token)}"
    )
    try:
        while True:
            data = await websocket.receive_bytes()
            await connection.handle_message(data)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001 - close the socket on any handler failure
        # e.g. a malformed msgpack frame: never leave the dead connection
        # registered (REVIEW.md #6).
        print(
            "[WS-Puryfi] Handler error for token "
            f"{token_fingerprint(user_link_token)}: {type(e).__name__}"
        )
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed
    finally:
        await manager.remove(user_link_token, connection)
        connection.fail_pending("connection closed")
        print(
            "[WS-Puryfi] Connection closed for token "
            f"{token_fingerprint(user_link_token)}"
        )
