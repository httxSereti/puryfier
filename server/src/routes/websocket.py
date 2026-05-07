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
    await websocket.accept()

    # connect WebSocket
    connection = Connection(websocket, user_link_token)
    manager.add(connection, user_link_token)

    print(f"[WS-Puryfi] Connection established for user_token: '{user_link_token}'")
    try:
        while True:
            data = await websocket.receive_bytes()
            await connection.handle_message(data)
    except WebSocketDisconnect:
        manager.remove(user_link_token=user_link_token)
        print(f"[WS-Puryfi] Connection closed for user_token: '{user_link_token}'")
