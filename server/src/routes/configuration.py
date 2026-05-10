from models.connection_manager import manager
import os
import requests
from cuid2 import cuid_wrapper
from fastapi import APIRouter, HTTPException
from models.chaster import PartnerGetSessionAuthRepDto, PartnerConfigurationForPublic
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionSessionSchema, ChasterExtensionConfigurationSchema, ChasterExtensionConfigSchema
from pprint import pprint

router = APIRouter(prefix="/api/configuration", tags=["configuration"])

developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")
cuid = cuid_wrapper()

@router.get("/{configuration_token}", response_model=ChasterExtensionConfigurationSchema)
async def configuration(configuration_token: str):
    """
        Get the configuration of the extension
    """
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}"
    }

    data: PartnerConfigurationForPublic | None = None

    try:
        response = requests.get(
            f"https://api.chaster.app/api/extensions/configurations/{configuration_token}",
            headers=headers
        )
        response.raise_for_status()
        data = PartnerConfigurationForPublic(**response.json())

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        raise HTTPException(status_code=status_code, detail=str(e))
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
            lock_on_freeze=data.config.get("lock_on_freeze", False),
            unlock_on_unfreeze=data.config.get("unlock_on_unfreeze", False),
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
            config=ChasterExtensionConfigSchema(
                lock_on_freeze=lock_config.lock_on_freeze,
                unlock_on_unfreeze=lock_config.unlock_on_unfreeze,
            ),
        )

        return configuration
    else:
        configuration = ChasterExtensionConfigurationSchema(
            id=str(lock_config.id),
            role=data.role,
            has_linked_plugin=lock_config.has_linked_plugin,
            is_online=manager.get_by_user_link_token(lock_config.link_token or "") is not None,
            has_session=True,
            config=ChasterExtensionConfigSchema(
                lock_on_freeze=lock_config.lock_on_freeze,
                unlock_on_unfreeze=lock_config.unlock_on_unfreeze,
            ),
        )

        return configuration

@router.put("/{configuration_token}")
async def update_configuration(configuration_token: str, payload: dict):
    """
        Update the configuration of the extension
    """
    developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.put(
            f"https://api.chaster.app/api/extensions/configurations/{configuration_token}",
            headers=headers,
            json={"config": payload}
        )
        response.raise_for_status()
        
        data = response.json()
        session_id = data.get("sessionId")
        pprint(data)
        print(f"[config-put] payload received: {payload}")
        print(f"[config-put] session_id from chaster: {session_id}")
        
        if session_id:
            lock_config = await UserLockConfiguration.find_one(
                UserLockConfiguration.session_id == session_id
            )
            if lock_config:
                print(f"[config-put] found lock_config id: {lock_config.id}")
                lock_config.lock_on_freeze = payload.get("lock_on_freeze", lock_config.lock_on_freeze)
                lock_config.unlock_on_unfreeze = payload.get("unlock_on_unfreeze", lock_config.unlock_on_unfreeze)
                await lock_config.save()
                print(f"[DB] Updated UserLockConfiguration for session {session_id!r}")
            else:
                print(f"[config-put] NO lock_config found for session_id: {session_id}")
        else:
            print(f"[config-put] NO session_id in response!")
            
        return {"status": "ok"}
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
