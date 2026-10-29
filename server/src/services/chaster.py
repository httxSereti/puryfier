import logging

import httpx

from utils import chaster_api

logger = logging.getLogger(__name__)


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
        logger.warning(
            "Could not add time to Chaster lock",
            extra={"chaster_session_id": session_id, "chaster_duration": duration},
            exc_info=True,
        )
        return False
