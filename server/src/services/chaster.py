import httpx

from utils import chaster_api


async def add_time_to_lock(session_id: str, duration: int) -> bool:
    """
        Add duration to a Chaster Lock using session id
    """
    try:
        response = await chaster_api.chaster_client.post(
            f"/api/extensions/sessions/{session_id}/action",
            json={
                "action": {
                    "name": "add_time",
                    "params": duration
                }
            },
        )
        return response.status_code == 201
    except httpx.HTTPError as e:
        print(f"Error adding duration: {e}")
        return False
