from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
from services.queue import queue_message
from utils.logging_config import get_logger
from utils.redaction import token_fingerprint

log = get_logger(__name__)


async def handle_lock_unfrozen(payload: dict) -> dict:
    """
    Handle the 'lock_unfrozen' event action from Chaster.
    """
    session_id = payload.get('data', {}).get('sessionId')

    if not session_id:
        log.warning("webhook.lock_unfrozen.no_session")
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_session"}
    
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )
    
    if not lock_config or not lock_config.config:
        log.warning("webhook.lock_unfrozen.no_config", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_config"}
        
    if not lock_config.link_token:
        log.warning("webhook.lock_unfrozen.no_link_token", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_link_token"}
        
    if not lock_config.config.unlock_on_unfreeze:
        log.debug("webhook.lock_unfrozen.disabled", session_id=session_id)
        return {"status": "ok", "action": "lock_unfrozen_ignored_config_false"}
        
    connection = manager.get_by_user_link_token(lock_config.link_token)

    # fetch lock_password from lock_config
    retrieved_password = lock_config.lock_password

    if not retrieved_password:
        # Never send {"secret": None} to the plugin (REVIEW.md #20).
        log.warning(
            "webhook.lock_unfrozen.no_password",
            session_id=session_id,
        )
        return {"status": "error", "error": "no_lock_password"}

    if connection:
        log.info(
            "webhook.lock_unfrozen.connection_found",
            session_id=session_id,
            link_token=token_fingerprint(lock_config.link_token),
        )
        # disable Puryfi
        unlockResponse = await connection.send_message("enterLockPassword", {"secret": retrieved_password})

        if unlockResponse.get('type') == 'ok':
            await connection.send_message("setState", {"path": "enabled", "value": False})
        else:
            error = unlockResponse.get('error', 'unknown_error') if isinstance(unlockResponse, dict) else 'unknown_error'
            log.warning(
                "webhook.lock_unfrozen.failed",
                session_id=session_id,
                error=error,
            )
            return {"status": "error", "error": error}

        log.info(
            "webhook.lock_unfrozen.processed",
            session_id=session_id,
        )

        return {"status": "ok", "action": "lock_unfrozen_processed"}
    else:
        log.info(
            "webhook.lock_unfrozen.queued",
            session_id=session_id,
            link_token=token_fingerprint(lock_config.link_token),
        )
        await queue_message(lock_config.link_token, "enterLockPassword", {"secret": retrieved_password})
        await queue_message(lock_config.link_token, "setState", {"path": "enabled", "value": False})
        return {"status": "ok", "action": "lock_unfrozen_queued_no_connection"}
