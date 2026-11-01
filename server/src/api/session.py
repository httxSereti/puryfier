"""HTTP endpoints for opening a Chaster session and managing its settings and link token."""

import httpx
from beanie.exceptions import CollectionWasNotInitialized
from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import PyMongoError

from api.deps import (
    get_chaster_gateway,
    get_puryfi_registry,
    get_session_repository,
)
from domain.entities import (
    ChasterExtensionConfigSchema,
    ChasterExtensionSessionSchema,
)
from domain.errors import PermissionDeniedError, SessionNotFoundError
from domain.ports import ChasterGateway, LockSessionRepository, PuryfiRegistry
from domain.use_cases.session import (
    create_link_token,
    open_session,
    update_session_configuration,
)

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/{main_token}", response_model=ChasterExtensionSessionSchema)
async def fetch_session(
    main_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    """Fetch a Chaster session and fetch-or-create its local configuration."""
    try:
        return await open_session(
            main_token,
            chaster=chaster,
            sessions=sessions,
            puryfi=puryfi,
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502, detail="Invalid configuration from Chaster"
        ) from e
    except (CollectionWasNotInitialized, PyMongoError) as e:
        raise HTTPException(
            status_code=500, detail="Unable to fetch lock_config"
        ) from e


@router.put("/{main_token}/configuration")
async def update_session_configuration_endpoint(
    main_token: str,
    payload: ChasterExtensionConfigSchema,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    """Update the settings of the current session from the main page."""
    try:
        await update_session_configuration(
            main_token,
            payload,
            chaster=chaster,
            sessions=sessions,
            puryfi=puryfi,
        )
        return {"status": "ok"}
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Chaster rejected the configuration update",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail="Chaster API is unavailable"
        ) from e
    except (CollectionWasNotInitialized, PyMongoError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=500, detail="Internal server error"
        ) from e


@router.post(
    "/{main_token}/link-token", response_model=ChasterExtensionSessionSchema
)
async def create_link_token_endpoint(
    main_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
):
    """Generate (or reuse) the wearer's Puryfi link token."""
    try:
        return await create_link_token(
            main_token,
            chaster=chaster,
            sessions=sessions,
        )
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (CollectionWasNotInitialized, PyMongoError) as e:
        raise HTTPException(status_code=500, detail="Internal server error") from e
