import os

import httpx
from fastapi import HTTPException

CHASTER_BASE_URL = "https://api.chaster.app"

# One shared async client for all Chaster API calls (see REVIEW.md #4).
# Always access it via the module (`chaster_api.chaster_client`) so tests can
# swap it with a mock-transport client.
chaster_client = httpx.AsyncClient(
    base_url=CHASTER_BASE_URL,
    headers={
        "accept": "application/json",
        "Authorization": f"Bearer {os.getenv('CHASTER_DEVELOPER_TOKEN', '')}",
    },
    timeout=10.0,
)


async def close_chaster_client() -> None:
    """Close the shared client (called from the app lifespan shutdown)."""
    await chaster_client.aclose()


async def get_session_auth(main_token: str) -> dict:
    """
    GET /api/extensions/auth/sessions/{main_token}

    Returns the parsed Chaster session payload. Raises HTTPException with the
    upstream status code on failure.
    """
    try:
        response = await chaster_client.get(f"/api/extensions/auth/sessions/{main_token}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Chaster API error: {e}")


async def create_custom_log(session_id: str, title: str, description: str, role: str, icon: str = "link", color: str = "#ffffff") -> bool:
    """
    POST /api/extensions/sessions/{sessionId}/logs/custom
    Create a custom log entry for an extension lock session.
    """

    payload = {
        "role": role,
        "icon": icon,
        "color": color,
        "title": title,
        "description": description,
    }

    try:
        response = await chaster_client.post(
            f"/api/extensions/sessions/{session_id}/logs/custom",
            json=payload,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"[Chaster] Error creating custom log: {e}")
        return False
