import httpx
from beanie.exceptions import CollectionWasNotInitialized
from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionConfigSchema, ChasterExtensionConfigurationSchema
from services.lock_configuration import get_or_create_lock_configuration
from typings.chaster import PartnerConfigurationForPublic
from utils import chaster_api
from utils.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/configuration", tags=["configuration"])

@router.get("/{configuration_token}", response_model=ChasterExtensionConfigurationSchema)
async def configuration(configuration_token: str):
    """
        Get the configuration of the extension
    """
    data: PartnerConfigurationForPublic | None = None

    try:
        response = await chaster_api.request_chaster(
            "GET", f"/api/extensions/configurations/{configuration_token}"
        )
        response.raise_for_status()
        data = PartnerConfigurationForPublic(**response.json())

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
        raise HTTPException(status_code=500, detail="Internal server error") from e

    try:
        chaster_config = ChasterExtensionConfigSchema(**(data.config or {}))
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502, detail="Invalid configuration from Chaster"
        ) from e

    # no lock active, shared-lock or self-lock so use chaster to save configuration
    if not data.sessionId:
        return ChasterExtensionConfigurationSchema(
            id="",
            role=data.role,
            config=chaster_config,
            has_session=False
        )   
    
    # Fetch or create atomically: concurrent config/session requests for the
    # same session must never create duplicate documents.
    try:
        lock_config = await get_or_create_lock_configuration(
            data.sessionId,
            # Use the config from Chaster (self-lock or shared-lock).
            config=chaster_config,
        )
    except (CollectionWasNotInitialized, PyMongoError) as e:
        raise HTTPException(status_code=500, detail="Unable to fetch lock_config") from e
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502, detail="Invalid configuration from Chaster"
        ) from e
    
    if data.role == "wearer":
        configuration = ChasterExtensionConfigurationSchema(
            id=str(lock_config.id),
            role=data.role,
            has_linked_plugin=lock_config.has_linked_plugin,
            is_online=manager.is_online(lock_config.link_token or ""),
            link_token=lock_config.link_token,
            has_session=True,
            config=lock_config.config,
        )

        return configuration
    else:
        configuration = ChasterExtensionConfigurationSchema(
            id=str(lock_config.id),
            role=data.role,
            has_linked_plugin=lock_config.has_linked_plugin,
            is_online=manager.is_online(lock_config.link_token or ""),
            has_session=True,
            config=lock_config.config,
        )

        return configuration

@router.put("/{configuration_token}")
async def update_configuration(
    configuration_token: str, payload: ChasterExtensionConfigSchema
):
    """
        Update the configuration of the extension.

        The body is validated before Chaster is called, and the validated
        payload is the local source of truth even if Chaster omits `config`
        from its response.
    """
    try:
        response = await chaster_api.request_chaster(
            "PUT",
            f"/api/extensions/configurations/{configuration_token}",
            json={"config": payload.model_dump()},
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Unexpected Chaster response")
        session_id = data.get("sessionId")
        # Not logging the full Chaster response: it contains user data (REVIEW.md #13).
        log.info("configuration.session_resolved", session_id=session_id)

        if session_id:
            lock_config = await UserLockConfiguration.find_one(
                UserLockConfiguration.session_id == session_id
            )
            if lock_config:
                log.info(
                    "configuration.lock_config_found",
                    session_id=session_id,
                    lock_config_id=str(lock_config.id),
                )

                lock_config.config = payload
                await lock_config.save()

                await manager.update_cached_config(
                    lock_config.link_token or "", lock_config.config
                )
                log.info("configuration.updated", session_id=session_id)
            else:
                log.warning(
                    "configuration.no_lock_config",
                    session_id=session_id,
                )
        else:
            log.warning("configuration.no_session_id")

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
        raise HTTPException(status_code=500, detail="Internal server error") from e
