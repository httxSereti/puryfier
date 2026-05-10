from models.connection_manager import manager
import os
import requests
from cuid2 import cuid_wrapper
from fastapi import APIRouter, HTTPException
from models.chaster import PartnerGetSessionAuthRepDto, PartnerConfigurationForPublic
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionSessionSchema, ChasterExtensionConfigurationSchema, ChasterExtensionConfigSchema
from pprint import pprint

router = APIRouter(prefix="/api/session", tags=["session"])

developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")
cuid = cuid_wrapper()

@router.get("/{main_token}", response_model=ChasterExtensionSessionSchema)
async def fetch_session(main_token: str):
    """
        Fetch Chaster session and create a UserLockConfiguration for it
        using the Developer Token and main_token issued when opening iframe on chaster app
    """

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}"
    }

    data: PartnerGetSessionAuthRepDto | None = None

    try:
        response = requests.get(
            f"https://api.chaster.app/api/extensions/auth/sessions/{main_token}",
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


@router.post("/{session_id}/link-token", response_model=ChasterExtensionSessionSchema)
async def create_link_token(session_id: str):
    """
        Generate a unique link_token for the UserLockConfiguration identified by session_id.
        Returns the existing token if one already exists.
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
