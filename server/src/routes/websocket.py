from models.documents import UserLockConfiguration
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from models.connection import Connection
from models.connection_manager import manager

router = APIRouter()


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
    except Exception as e:
        print(f"[WS-Puryfi] Error fetching user lock configuration: {e}")
        await websocket.close(code=1011)
        return

    if user_lock_config is None:
        print(f"[WS-Puryfi] User lock configuration not found for user_token: '{user_link_token}'")
        await websocket.close(code=4004)
        return

    await websocket.accept()

    # connect WebSocket
    connection = Connection(websocket, user_lock_config)
    manager.add(connection, user_link_token)

    print(f"[WS-Puryfi] Connection established for user_token: '{user_link_token}'")
    try:
        while True:
            data = await websocket.receive_bytes()
            await connection.handle_message(data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # e.g. a malformed msgpack frame: never leave the dead connection
        # registered (REVIEW.md #6).
        print(f"[WS-Puryfi] Handler error for user_token '{user_link_token}': {e}")
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed
    finally:
        manager.remove(user_link_token)
        connection.fail_pending("connection closed")
        print(f"[WS-Puryfi] Connection closed for user_token: '{user_link_token}'")
