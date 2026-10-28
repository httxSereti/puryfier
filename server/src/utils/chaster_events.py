from typing import Any


def _event_data(payload: dict) -> dict[str, Any] | None:
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def extract_session_id(payload: dict) -> str | None:
    """Read the session id from either `data.session.sessionId` or `data.sessionId`."""
    data = _event_data(payload)
    if data is None:
        return None

    session = data.get("session")
    if isinstance(session, dict):
        session_id = session.get("sessionId")
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()

    session_id = data.get("sessionId")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()

    return None


def extract_session_updated_at(payload: dict) -> str | None:
    data = _event_data(payload)
    if data is None:
        return None

    session = data.get("session")
    if isinstance(session, dict):
        updated_at = session.get("updatedAt")
    else:
        updated_at = data.get("updatedAt")

    if isinstance(updated_at, str) and updated_at.strip():
        return updated_at.strip()
    return None
