from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
import secrets
from services.queue import queue_message

async def handle_lock_frozen(payload: dict) -> dict:
    """
    Handle the 'lock_frozen' event action from Chaster.
    """   
    session_id = payload['data']['sessionId']
    
    if not session_id:
        print("[lock_frozen] Error: Could not find sessionId in payload.")
        return {"status": "ok", "action": "lock_frozen_ignored_no_session"}
    
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )
    
    if not lock_config:
        print(f"[lock_frozen] No UserLockConfiguration found for session {session_id}")
        return {"status": "ok", "action": "lock_frozen_ignored_no_config"}
        
    if not lock_config.link_token:
        print(f"[lock_frozen] No link_token in UserLockConfiguration for session {session_id}")
        return {"status": "ok", "action": "lock_frozen_ignored_no_link_token"}
        
    if not lock_config.lock_on_freeze:
        print(f"[lock_frozen] lock_on_freeze is False for session {session_id}, ignoring.")
        return {"status": "ok", "action": "lock_frozen_ignored_config_false"}
        
    connection = manager.get_by_user_link_token(lock_config.link_token)
    
    generated_password = secrets.token_urlsafe(16)
    lock_config.lock_password = generated_password
    await lock_config.save()
    
    if connection:
        print(f"[lock_frozen] Found connection for link_token {lock_config.link_token}")
        # enable Puryfi
        await connection.send_message("setState", {"path": "enabled", "value": True})
        await connection.send_message("setState", {
            "path": "lockConfiguration", 
            "value": {
                "password": {"secret": generated_password}
            }
        })
    
        return {"status": "ok", "action": "lock_frozen_processed"}
    else:
        print(f"[lock_frozen] No connection found for link_token {lock_config.link_token}. Queuing message.")
        await queue_message(lock_config.link_token, "setState", {"path": "enabled", "value": True})
        await queue_message(lock_config.link_token, "setState", {
            "path": "lockConfiguration", 
            "value": {
                "password": {"secret": generated_password}
            }
        })
        return {"status": "ok", "action": "lock_frozen_queued_no_connection"}

    return {"status": "ok", "action": "lock_frozen_processed"}
