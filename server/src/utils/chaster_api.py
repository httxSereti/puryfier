import os
import requests

developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")

def create_custom_log(session_id: str, title: str, description: str, role: str, icon: str = "link", color: str = "#ffffff") -> bool:
    """
    POST /api/extensions/sessions/{sessionId}/logs/custom
    Create a custom log entry for an extension lock session.
    """

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "role": role,
        "icon": icon,
        "color": color,
        "title": title,
        "description": description,
    }

    try:
        response = requests.post(
            url=f"https://api.chaster.app/api/extensions/sessions/{session_id}/logs/custom",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[Chaster] Error creating custom log: {e}")
        return False
