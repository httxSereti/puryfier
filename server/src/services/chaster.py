import os
import requests

developer_token = os.getenv("CHASTER_DEVELOPER_TOKEN", "")

def add_time_to_lock(session_id: str, duration: int) -> bool:
    """
        Add duration to a Chaster Lock using session id
    """
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {developer_token}",
        "Content-Type": "application/json",
    }

    try:
        data = requests.post(
            url=f"https://api.chaster.app/api/extensions/sessions/{session_id}/action",
            headers=headers,
            json={
                "action": {
                    "name": "add_time",
                    "params": duration
                }
            },
        )
        data.raise_for_status()
        
        if data.status_code == 201:
            return True
        else:
            return False
    except Exception as e:
        print(f"Error adding duration: {e}")
        return False