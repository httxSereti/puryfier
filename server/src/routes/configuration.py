from models.connection_manager import manager
import httpx
from fastapi import APIRouter, HTTPException
from typings.chaster import PartnerConfigurationForPublic
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionConfigurationSchema
from utils import chaster_api

router = APIRouter(prefix="/api/configuration", tags=["configuration"])

@router.get("/{configuration_token}", response_model=ChasterExtensionConfigurationSchema)
async def configuration(configuration_token: str):
    """
        Get the configuration of the extension
    """
    data: PartnerConfigurationForPublic | None = None

    try:
        response = await chaster_api.chaster_client.get(
            f"/api/extensions/configurations/{configuration_token}"
        )
        response.raise_for_status()
        data = PartnerConfigurationForPublic(**response.json())

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Chaster API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

    # no lock active, shared-lock or self-lock so use chaster to save configuration
    if not data.sessionId:
        return ChasterExtensionConfigurationSchema(
            id="",
            role=data.role,
            config=data.config,
            has_session=False
        )   
    
    # fetch lock_config for session_id
    try:
        lock_config = await UserLockConfiguration.find_one(
            UserLockConfiguration.session_id == data.sessionId
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unable to fetch lock_config")
    
    # if no lock_config found, create one
    if lock_config is None:
        # use the configuration from chaster (if it self lock or shared lock)
        lock_config = UserLockConfiguration(
            session_id=data.sessionId,
            config=data.config
        )
        await lock_config.insert()
        print(f"[DB] Created UserLockConfiguration for wearer session {data.sessionId!r} via config hook")
    
    if data.role == "wearer":
        configuration = ChasterExtensionConfigurationSchema(
            id=str(lock_config.id),
            role=data.role,
            has_linked_plugin=lock_config.has_linked_plugin,
            is_online=manager.get_by_user_link_token(lock_config.link_token or "") is not None,
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
            is_online=manager.get_by_user_link_token(lock_config.link_token or "") is not None,
            has_session=True,
            config=lock_config.config,
        )

        return configuration

@router.put("/{configuration_token}")
async def update_configuration(configuration_token: str, payload: dict):
    """
        Update the configuration of the extension
    """
    try:
        response = await chaster_api.chaster_client.put(
            f"/api/extensions/configurations/{configuration_token}",
            json={"config": payload}
        )
        response.raise_for_status()

        data = response.json()
        session_id = data.get("sessionId")
        # Not logging the full Chaster response: it contains user data (REVIEW.md #13).
        print(f"[config-put] session_id from chaster: {session_id}")

        if session_id:
            lock_config = await UserLockConfiguration.find_one(
                UserLockConfiguration.session_id == session_id
            )
            if lock_config:
                print(f"[config-put] found lock_config id: {lock_config.id}")

                lock_config.config = data.get("config")
                await lock_config.save()

                manager.update_cached_config(lock_config.link_token or "", lock_config.config)
                print(f"[DB] Updated UserLockConfiguration for session {session_id!r}")
            else:
                print(f"[config-put] NO lock_config found for session_id: {session_id}")
        else:
            print(f"[config-put] NO session_id in response!")

        return {"status": "ok"}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Chaster API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
