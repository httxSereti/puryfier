from models.connection_manager import manager
from models.documents.user_lock_configuration import UserLockConfiguration
from services.queue import queue_message

async def handle_lock_unfrozen(payload: dict) -> dict:
    """
    Handle the 'lock_unfrozen' event action from Chaster.
    """
    session_id = payload['data']['sessionId']
    
    if not session_id:
        print("[lock_unfrozen] Error: Could not find sessionId in payload.")
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_session"}
    
    lock_config = await UserLockConfiguration.find_one(
        UserLockConfiguration.session_id == session_id
    )
    
    if not lock_config:
        print(f"[lock_unfrozen] No UserLockConfiguration found for session {session_id}")
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_config"}
        
    if not lock_config.link_token:
        print(f"[lock_unfrozen] No link_token in UserLockConfiguration for session {session_id}")
        return {"status": "ok", "action": "lock_unfrozen_ignored_no_link_token"}
        
    if not lock_config.unlock_on_unfreeze:
        print(f"[lock_unfrozen] unlock_on_unfreeze is False for session {session_id}, ignoring.")
        return {"status": "ok", "action": "lock_unfrozen_ignored_config_false"}
        
    connection = manager.get_by_user_link_token(lock_config.link_token)
    
    # fetch lock_password from lock_config
    retrieved_password = lock_config.lock_password
    
    if connection:
        print(f"[lock_unfrozen] Found connection for link_token {lock_config.link_token}")
        # disable Puryfi
        unlockResponse = await connection.send_message("enterLockPassword", {"secret": retrieved_password})
        
        if unlockResponse['type'] == 'ok':
            disableResponse = await connection.send_message("setState", {"path": "enabled", "value": False})
        else:
            print(f"[lock_unfrozen] Failed to unlock lock '{session_id}', error: {unlockResponse['error']}")
            return {"status": "error", "error": unlockResponse['error']}

        print(f"[lock_unfrozen] Sent messages to connection: {unlockResponse}, {disableResponse}")
    
        return {"status": "ok", "action": "lock_unfrozen_processed"}
    else:
        print(f"[lock_unfrozen] No connection found for link_token {lock_config.link_token}. Queuing message.")
        await queue_message(lock_config.link_token, "enterLockPassword", {"secret": retrieved_password})
        await queue_message(lock_config.link_token, "setState", {"path": "enabled", "value": False})
        return {"status": "ok", "action": "lock_unfrozen_queued_no_connection"}

    return {"status": "ok", "action": "lock_unfrozen_processed"}
