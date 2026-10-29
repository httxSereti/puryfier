from cuid2 import cuid_wrapper
from fastapi import APIRouter, HTTPException

from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
from schemas import ChasterExtensionConfigSchema, ChasterExtensionSessionSchema
from services.lock_configuration import get_or_create_lock_configuration
from typings.chaster import PartnerGetSessionAuthRepDto
from utils.chaster_api import get_session_auth
from utils.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/session", tags=["session"])

cuid = cuid_wrapper()

@router.get("/{main_token}", response_model=ChasterExtensionSessionSchema)
async def fetch_session(main_token: str):
    """
        Fetch Chaster session and create a UserLockConfiguration for it
        using the Developer Token and main_token issued when opening iframe on chaster app
    """

    data: PartnerGetSessionAuthRepDto | None = None

    data = await get_session_auth(main_token)
    # Not logging the payload: it contains user objects and config (REVIEW.md #13).

    # Fetch or create a UserLockConfiguration for this Chaster session
    session_id: str = data.get("session", {}).get("sessionId", "")
    lock_id: str = data.get("session", {}).get("lock", {}).get("_id", "")
    keyholder = data.get("session", {}).get("lock", {}).get("keyholder")
    keyholder_id: str | None = keyholder.get("_id") if isinstance(keyholder, dict) else None
    wearer = data.get("session", {}).get("lock", {}).get("user")
    wearer_id: str | None = wearer.get("_id") if isinstance(wearer, dict) else None

    try:
        config = ChasterExtensionConfigSchema(
            **data.get("session", {}).get("config", {}),
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=502, detail="Invalid configuration from Chaster"
        ) from e

    lock_config = await get_or_create_lock_configuration(
        session_id,
        config=config,
        lock_id=lock_id or None,
        keyholder_id=keyholder_id,
        wearer_id=wearer_id,
    )

    # Get if there is an active, fully-ready connection to this session.
    is_online = manager.is_online(lock_config.link_token or "")

    role = data.get("role", "")

    # Deny by default: only the keyholder may receive the emergency password.
    # Unknown or future roles must never get the cleartext secret.
    lock_password = lock_config.lock_password if role == "keyholder" else None

    return ChasterExtensionSessionSchema(
        id=str(lock_config.id),
        role=role,
        is_online=is_online,
        has_linked_plugin=lock_config.has_linked_plugin,
        # link_token only to the wearer: they own the Puryfi client, and
        # whoever holds the token owns the connection slot (REVIEW.md #8).
        link_token=lock_config.link_token if role == "wearer" else None,
        config=lock_config.config,
        lock_password=lock_password,
    )


@router.post("/{main_token}/link-token", response_model=ChasterExtensionSessionSchema)
async def create_link_token(main_token: str):
    """
        Generate a unique link_token for the session authenticated by main_token
        (the Chaster-issued token from the iframe URL). Returns the existing
        token if one already exists.

        Only the wearer may do this: the link token controls the Puryfi
        connection slot (REVIEW.md #8).
    """
    data = await get_session_auth(main_token)

    if data.get("role", "") != "wearer":
        raise HTTPException(status_code=403, detail="Only the wearer can manage the Puryfi link token")

    session_id: str = data.get("session", {}).get("sessionId", "")
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )
    if lock_config is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not lock_config.link_token:
        lock_config.link_token = cuid()
        await lock_config.save()
        log.info("link_token.created", session_id=session_id)

    return ChasterExtensionSessionSchema(
        id=str(lock_config.id),
        role="wearer",
        has_linked_plugin=lock_config.has_linked_plugin,
        link_token=lock_config.link_token,
        # lock_password deliberately omitted: the wearer must never receive
        # the cleartext password.
    )
