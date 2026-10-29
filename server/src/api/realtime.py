"""Realtime WebSocket endpoints (browser status + Puryfi plugin)."""

import asyncio

import httpx
from beanie.exceptions import CollectionWasNotInitialized
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pymongo.errors import PyMongoError

from api.deps import (
    get_chaster_gateway,
    get_session_repository,
)
from domain.entities import LockSession
from domain.ports import ChasterGateway, LockSessionRepository
from infra.logging import get_logger
from infra.redaction import token_fingerprint
from realtime.connection import Connection
from realtime.registry import manager
from realtime.watchers import watchers

log = get_logger(__name__)

router = APIRouter(prefix="/ws")

# Browser watchers only receive pushes, so a period of silence is normal.
# Send an application-level ping so dead sockets are detected and removed.
WATCHER_HEARTBEAT_SECONDS = 30.0


async def watch_session(
    websocket: WebSocket,
    session_id: str,
    lock_config: LockSession,
) -> None:
    """Stream the Puryfi connection status of a session to a browser socket."""
    await websocket.accept()
    watchers.add(session_id, websocket)

    try:
        # Always send the current state first: the page may have been opened
        # while Puryfi was already connected.
        await websocket.send_json(manager.status_for_lock_config(lock_config))

        while True:
            try:
                # The page only listens; use a timeout to send heartbeats and
                # detect sockets that silently died.
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WATCHER_HEARTBEAT_SECONDS,
                )
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("ws.watcher.failed", exc_info=True)
    finally:
        watchers.remove(session_id, websocket)


@router.websocket("/session/{main_token}")
async def session_status_endpoint(
    websocket: WebSocket,
    main_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
):
    """Realtime Puryfi status for the extension main page."""
    try:
        data = await chaster.get_session_auth(main_token)
    except HTTPException as e:
        log.warning(
            "ws.session.auth_rejected",
            status_code=e.status_code,
        )
        await websocket.close(code=4004)
        return
    except Exception:
        log.warning(
            "ws.session.auth_failed",
            link_token=token_fingerprint(main_token),
            exc_info=True,
        )
        await websocket.close(code=1011)
        return

    if not data.session_id:
        await websocket.close(code=4004)
        return

    try:
        lock_config = await sessions.get_by_session_id(data.session_id)
    except (CollectionWasNotInitialized, PyMongoError):
        log.exception(
            "ws.lock_config_failed",
            session_id=data.session_id,
        )
        await websocket.close(code=1011)
        return

    if lock_config is None:
        await websocket.close(code=4004)
        return

    await watch_session(websocket, data.session_id, lock_config)


@router.websocket("/configuration/{configuration_token}")
async def configuration_status_endpoint(
    websocket: WebSocket,
    configuration_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
):
    """Realtime Puryfi status for the extension configuration page."""
    try:
        data = await chaster.get_configuration(configuration_token)
    except httpx.HTTPStatusError as e:
        log.warning(
            "ws.configuration.auth_rejected",
            status_code=e.response.status_code,
        )
        await websocket.close(code=4004)
        return
    except httpx.HTTPError:
        log.warning(
            "ws.configuration.fetch_failed",
            configuration_token=token_fingerprint(configuration_token),
            exc_info=True,
        )
        await websocket.close(code=1011)
        return
    except (TypeError, ValueError):
        log.warning(
            "ws.configuration.invalid_response",
            configuration_token=token_fingerprint(configuration_token),
            exc_info=True,
        )
        await websocket.close(code=1011)
        return

    if not data.session_id:
        await websocket.close(code=4004)
        return

    try:
        lock_config = await sessions.get_by_session_id(data.session_id)
    except (CollectionWasNotInitialized, PyMongoError):
        log.exception(
            "ws.lock_config_failed",
            session_id=data.session_id,
        )
        await websocket.close(code=1011)
        return

    if lock_config is None:
        await websocket.close(code=4004)
        return

    await watch_session(websocket, data.session_id, lock_config)


@router.websocket("/{user_link_token}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_link_token: str,
    sessions: LockSessionRepository = Depends(get_session_repository),
):
    """Handle WebSocket connections from the Puryfi plugin."""
    # Validate the token BEFORE accepting the connection.
    try:
        user_lock_config = await sessions.get_by_link_token(user_link_token)
    except (CollectionWasNotInitialized, PyMongoError):
        log.exception(
            "ws.plugin.lock_config_failed",
            link_token=token_fingerprint(user_link_token),
        )
        await websocket.close(code=1011)
        return

    if user_lock_config is None:
        log.warning(
            "ws.plugin.unknown_token",
            link_token=token_fingerprint(user_link_token),
        )
        await websocket.close(code=4004)
        return

    await websocket.accept()

    # Connect the WebSocket actor.
    connection = Connection(websocket, user_lock_config)
    await connection.start()
    try:
        await manager.add(connection, user_link_token)

        log.info(
            "ws.plugin.connected",
            session_id=user_lock_config.session_id,
            link_token=token_fingerprint(user_link_token),
        )
        while True:
            data = await websocket.receive_bytes()
            await connection.handle_message(data)
    except WebSocketDisconnect:
        pass
    except Exception:
        # e.g. a malformed msgpack frame: never leave the dead connection
        # registered.
        log.exception(
            "ws.plugin.handler_failed",
            link_token=token_fingerprint(user_link_token),
        )
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed
    finally:
        # TestClient/uvicorn may cancel the endpoint task as soon as the
        # client disconnects. Shield the cleanup so the offline status is
        # still published and the connection is unregistered.
        async def _cleanup() -> None:
            await connection.stop()
            await manager.remove(user_link_token, connection)
            log.info(
                "ws.plugin.disconnected",
                session_id=user_lock_config.session_id,
                link_token=token_fingerprint(user_link_token),
            )

        cleanup_task = asyncio.create_task(_cleanup(), name="puryfi-cleanup")
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await cleanup_task
            raise
