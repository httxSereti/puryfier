"""Chaster webhook event parsing and business idempotency keys."""

from typing import Any

from domain.errors import InvalidWebhookPayloadError


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


def _stringify_id(value: object) -> str | None:
    """Normalize a Chaster identifier to a stable non-empty string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)):
        normalized = str(value).strip()
        return normalized or None
    # JSON encoders sometimes wrap ObjectIds as {"$oid": "..."}.
    if isinstance(value, dict):
        oid = value.get("$oid")
        if isinstance(oid, str):
            return oid.strip() or None
    return None


def build_event_key(data: dict) -> str | None:
    """Derive the business idempotency key for a Chaster webhook.

    Never uses requestId: Chaster generates a new one for every retry.
    Returns None when the event has no stable business identity (for example an
    unknown event), in which case there is nothing stateful to deduplicate.
    """
    event = data.get("event")
    if not isinstance(event, str) or not event:
        return None

    event_data = data.get("data")
    if not isinstance(event_data, dict):
        return None

    if event == "action_log.created":
        action_log = event_data.get("actionLog")
        action_id = (
            _stringify_id(action_log.get("_id"))
            if isinstance(action_log, dict)
            else None
        )
        if action_id is None:
            raise InvalidWebhookPayloadError(
                "Missing required key: 'data.actionLog._id'"
            )
        return f"{event}:{action_id}"

    if event.startswith("extension_session."):
        session_id = extract_session_id(data)
        if session_id is None:
            return None

        updated_at = extract_session_updated_at(data)
        if updated_at is not None:
            return f"{event}:{session_id}:{updated_at}"

        # Deleted is terminal and may not carry updatedAt; the session id is
        # still a stable business key.
        if event == "extension_session.deleted":
            return f"{event}:{session_id}"

        return None

    return None
