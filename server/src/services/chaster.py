import httpx

from utils import chaster_api
from utils.logging_config import get_logger

log = get_logger(__name__)


async def add_time_to_lock(session_id: str, duration: int) -> bool:
    """
        Add duration to a Chaster Lock using session id
    """
    try:
        response = await chaster_api.request_chaster(
            "POST",
            f"/api/extensions/sessions/{session_id}/action",
            json={
                "action": {
                    "name": "add_time",
                    "params": duration
                }
            },
        )
        return response.status_code == 201
    except httpx.HTTPError:
        log.warning(
            "chaster.add_time_failed",
            chaster_session_id=session_id,
            duration=duration,
            exc_info=True,
        )
        return False
