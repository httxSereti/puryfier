import secrets

from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
from services.queue import queue_message
from utils.logging_config import get_logger
from utils.redaction import token_fingerprint

log = get_logger(__name__)


async def handle_lock_frozen(payload: dict) -> dict:
    """
    Handle the 'lock_frozen' event action from Chaster.
    """   
    session_id = payload.get('data', {}).get('sessionId')

    if not session_id:
        log.warning("webhook.lock_frozen.no_session")
        return {"status": "ok", "action": "lock_frozen_ignored_no_session"}
    
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )
    
    if not lock_config or not lock_config.config:
        log.warning("webhook.lock_frozen.no_config", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_no_config"}
        
    if not lock_config.link_token:
        log.warning("webhook.lock_frozen.no_link_token", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_no_link_token"}
        
    if not lock_config.config.lock_on_freeze:
        log.debug("webhook.lock_frozen.disabled", session_id=session_id)
        return {"status": "ok", "action": "lock_frozen_ignored_config_false"}
        
    connection = manager.get_by_user_link_token(lock_config.link_token)
    
    generated_password = secrets.token_urlsafe(16)
    lock_config.lock_password = generated_password
    await lock_config.save()
    
    if connection:
        log.info(
            "webhook.lock_frozen.connection_found",
            session_id=session_id,
            link_token=token_fingerprint(lock_config.link_token),
        )
        # Send both state changes as one ordered mailbox batch: no other
        # command can interleave between enabling Puryfi and setting its lock.
        await connection.send_messages([
            ("setState", {"path": "enabled", "value": True}),
            (
                "setState",
                {
                    "path": "lockConfiguration",
                    "value": {"password": {"secret": generated_password}},
                },
            ),
        ])
    
        return {"status": "ok", "action": "lock_frozen_processed"}
    else:
        log.info(
            "webhook.lock_frozen.queued",
            session_id=session_id,
            link_token=token_fingerprint(lock_config.link_token),
        )
        await queue_message(lock_config.link_token, "setState", {"path": "enabled", "value": True})
        await queue_message(lock_config.link_token, "setState", {
            "path": "lockConfiguration", 
            "value": {
                "password": {"secret": generated_password}
            }
        })
        return {"status": "ok", "action": "lock_frozen_queued_no_connection"}
