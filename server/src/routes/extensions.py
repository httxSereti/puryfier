from models.connection_manager import manager
import os
import requests
from cuid2 import cuid_wrapper
from fastapi import APIRouter, HTTPException
from models.chaster import PartnerGetSessionAuthRepDto, PartnerConfigurationForPublic
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionSessionSchema, ChasterExtensionConfigurationSchema, ChasterExtensionConfigSchema
from pprint import pprint

router = APIRouter(prefix="/api/extensions", tags=["extensions"])

developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")
cuid = cuid_wrapper()

@router.get("/auth/sessions/{mainToken}", response_model=ChasterExtensionSessionSchema)
async def fetch_session(mainToken: str):
    """
        Fetch Chaster session and create a UserLockConfiguration for it
        using the Developer Token and mainToken issued when opening iframe on chaster app
    """

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}"
    }

    data: PartnerGetSessionAuthRepDto | None = None

    try:
        response = requests.get(
            f"https://api.chaster.app/api/extensions/auth/sessions/{mainToken}",
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        pprint(data)
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

    # Fetch or create a UserLockConfiguration for this Chaster session
    session_id: str = data.get("session", {}).get("sessionId", "")
    lock_id: str = data.get("session", {}).get("lock", {}).get("_id", "")
    keyholder = data.get("session", {}).get("lock", {}).get("keyholder")
    keyholder_id: str | None = keyholder.get("_id") if isinstance(keyholder, dict) else None
    wearer = data.get("session", {}).get("lock", {}).get("user")
    wearer_id: str | None = wearer.get("_id") if isinstance(wearer, dict) else None

    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )

    if lock_config is None:
        # if no lock_config found, create one
        lock_config = UserLockConfiguration(
            session_id=session_id,
            lock_id=lock_id or None,
            keyholder_id=keyholder_id,
            wearer_id=wearer_id,
            lock_on_freeze=data.get("session", {}).get("config", {}).get("lock_on_freeze", False),
            unlock_on_unfreeze=data.get("session", {}).get("config", {}).get("unlock_on_unfreeze", False),
        )
        await lock_config.insert()
        print(f"[DB] Created UserLockConfiguration for session {lock_id!r}")

    # get if there is an active connection to this session
    is_online = manager.get_by_user_link_token(lock_config.link_token or "")

    # send lockpassword in clear only to keyholder
    lock_password = lock_config.lock_password
    if data.get("role", "") == "wearer" and lock_password:
        lock_password = "HIDDEN"

    return ChasterExtensionSessionSchema(
        id=str(lock_config.id),
        role=data.get("role", ""),
        is_online=is_online is not None,
        has_linked_plugin=lock_config.has_linked_plugin,
        link_token=lock_config.link_token,
        lock_on_freeze=lock_config.lock_on_freeze,
        unlock_on_unfreeze=lock_config.unlock_on_unfreeze,
        lock_password=lock_password,
    )


@router.post("/sessions/{session_id}/link-token", response_model=ChasterExtensionSessionSchema)
async def create_link_token(session_id: str):
    """
        Generate a unique link_token for the UserLockConfiguration identified by session_id.
        Idempotent: returns the existing token if one already exists.
    """
    lock_config = await UserLockConfiguration.get(session_id)
    if lock_config is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not lock_config.link_token:
        lock_config.link_token = cuid()
        await lock_config.save()
        print(f"[DB] Generated link_token for session {session_id!r}")

    return ChasterExtensionSessionSchema(
        id=str(lock_config.id),
        role="",  # role not stored on the config row
        has_linked_plugin=lock_config.has_linked_plugin,
        link_token=lock_config.link_token,
        lock_on_freeze=lock_config.lock_on_freeze,
        unlock_on_unfreeze=lock_config.unlock_on_unfreeze,
        lock_password=lock_config.lock_password,
    )

@router.get("/configuration/{configurationToken}", response_model=ChasterExtensionConfigurationSchema)
async def configuration(configurationToken: str):
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
            f"https://api.chaster.app/api/extensions/configurations/{configurationToken}",
            headers=headers
        )
        response.raise_for_status()
        data = PartnerConfigurationForPublic(**response.json())

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

    print("\n\n[DATA]")
    pprint(data)

    # no lock active, shared-lock or self-lock so use chaster to save configuration
    if not data.sessionId:
        print('no active lock, using chaster to save configuration')
        schema = ChasterExtensionConfigurationSchema(
            id="",
            role=data.role,
            link_token=None,
            config=data.config
        )   
        pprint(schema)
        return schema
    
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
            is_online=manager.get_by_user_link_token(lock_config.link_token) is not None,
            link_token=lock_config.link_token,
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
            is_online=manager.get_by_user_link_token(lock_config.link_token) is not None,
            config=ChasterExtensionConfigSchema(
                lock_on_freeze=lock_config.lock_on_freeze,
                unlock_on_unfreeze=lock_config.unlock_on_unfreeze,
            ),
        )

        return configuration

@router.put("/configuration/{configurationToken}")
async def update_configuration(configurationToken: str, payload: dict):
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
            f"https://api.chaster.app/api/extensions/configurations/{configurationToken}",
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
