from services.session_lifecycle import revoke_session
from utils.chaster_events import extract_session_id


async def handle_extension_session_deleted(payload: dict) -> dict:
    """Purge everything tied to a Chaster session that has ended."""
    session_id = extract_session_id(payload)
    if not session_id:
        print("[extension_session.deleted] Missing sessionId in payload.")
        return {
            "status": "ok",
            "action": "extension_session_deleted_ignored_no_session",
        }

    deleted = await revoke_session(session_id)
    if not deleted:
        return {
            "status": "ok",
            "action": "extension_session_deleted_ignored_no_config",
        }

    return {"status": "ok", "action": "extension_session_deleted_processed"}
