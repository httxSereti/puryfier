"""HTTP endpoints for reading and updating the extension configuration."""

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
    ChasterExtensionConfigurationSchema,
)
from domain.ports import ChasterGateway, LockSessionRepository, PuryfiRegistry
from domain.use_cases.configuration import (
    get_configuration as get_configuration_use_case,
)
from domain.use_cases.configuration import (
    update_configuration as update_configuration_use_case,
)

router = APIRouter(prefix="/api/configuration", tags=["configuration"])


@router.get(
    "/{configuration_token}",
    response_model=ChasterExtensionConfigurationSchema,
)
async def configuration(
    configuration_token: str,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    """Get the configuration of the extension."""
    try:
        return await get_configuration_use_case(
            configuration_token,
            chaster=chaster,
            sessions=sessions,
            puryfi=puryfi,
        )
    except httpx.HTTPStatusError as e:
        # Avoid str(e): httpx puts the request URL (and its token) in it.
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Chaster rejected the configuration token",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail="Chaster API is unavailable"
        ) from e
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502, detail="Invalid configuration from Chaster"
        ) from e
    except (CollectionWasNotInitialized, PyMongoError) as e:
        raise HTTPException(
            status_code=500, detail="Unable to fetch lock_config"
        ) from e


@router.put("/{configuration_token}")
async def update_configuration(
    configuration_token: str,
    payload: ChasterExtensionConfigSchema,
    chaster: ChasterGateway = Depends(get_chaster_gateway),
    sessions: LockSessionRepository = Depends(get_session_repository),
    puryfi: PuryfiRegistry = Depends(get_puryfi_registry),
):
    """Update the configuration of the extension.

    The body is validated before Chaster is called, and the validated payload
    is the local source of truth even if Chaster omits ``config`` from its
    response.
    """
    try:
        await update_configuration_use_case(
            configuration_token,
            payload,
            chaster=chaster,
            sessions=sessions,
            puryfi=puryfi,
        )
        return {"status": "ok"}
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
