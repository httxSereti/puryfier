import json
import logging
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from utils.chaster_events import extract_session_id, extract_session_updated_at
from workers.webhook_inbox import webhook_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhook"])
security = HTTPBasic()

WEBHOOK_USER_ENV = "CHASTER_WEBHOOK_USER"
WEBHOOK_PWD_ENV = "CHASTER_WEBHOOK_PWD"


class WebhookCredentialsNotConfigured(RuntimeError):
    """Raised when the Chaster webhook credentials are missing or blank."""


def get_webhook_credentials() -> tuple[str, str]:
    """Return the configured webhook credentials, or fail closed.

    Empty credentials used to make ``Authorization: Basic Og==`` (empty user
    and password) valid. Both values are now mandatory: we reject blank values
    instead of comparing against them.
    """
    expected_user = os.getenv(WEBHOOK_USER_ENV, "")
    expected_pwd = os.getenv(WEBHOOK_PWD_ENV, "")

    if not expected_user.strip() or not expected_pwd.strip():
        raise WebhookCredentialsNotConfigured(
            f"{WEBHOOK_USER_ENV} and {WEBHOOK_PWD_ENV} must both be set and non-empty; "
            "the Chaster webhook endpoint is disabled until they are configured."
        )

    return expected_user, expected_pwd


def validate_webhook_credentials() -> None:
    """Refuse to start the application when webhook auth is not configured."""
    try:
        get_webhook_credentials()
    except WebhookCredentialsNotConfigured as exc:
        raise RuntimeError(str(exc)) from exc


def _stringify_id(value: object) -> str | None:
    """Normalize a Chaster identifier to a stable non-empty string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)):
        normalized = str(value).strip()
        return normalized or None
    # Beanie/Mongo JSON encoders sometimes wrap ObjectIds as {"$oid": "..."}.
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required key: 'data.actionLog._id'",
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


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    try:
        expected_user, expected_pwd = get_webhook_credentials()
    except WebhookCredentialsNotConfigured:
        # Defense in depth: even if startup validation is bypassed (tests,
        # embedded ASGI usage), never accept an unauthenticated webhook.
        logger.error("Chaster webhook credentials are not configured; rejecting request")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook authentication is not configured",
        )

    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"), expected_user.encode("utf8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"), expected_pwd.encode("utf8")
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.post("/extensions/chaster", status_code=status.HTTP_202_ACCEPTED)
async def chaster_webhook(request: Request, _: str = Depends(verify_credentials)):
    """
    Chaster webhook endpoint.

    Validates the payload and stores it in the durable inbox. Processing (and
    any slow Puryfi RPC) happens in the background worker, so Chaster's 10s
    timeout is never hit.
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON",
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be a JSON object",
        )

    event = data.get("event")
    request_id = data.get("requestId")

    if not event or not request_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required keys: 'event' and 'requestId'",
        )

    if event == "action_log.created":
        event_data = data.get("data")
        action_payload = (
            event_data.get("actionLog") if isinstance(event_data, dict) else None
        )
        action_type = (
            action_payload.get("type") if isinstance(action_payload, dict) else None
        )

        if not action_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required key: 'data.actionLog.type'",
            )

    # Business idempotency key: Chaster retries carry a new requestId every
    # time, so deduplicate on the event itself, never on requestId.
    event_key = build_event_key(data)

    if event_key is None:
        # Unknown event without a stable business identity: nothing stateful
        # to process, so acknowledge it without writing an inbox entry.
        return {"status": "ok", "action": "ignored_no_event_key"}

    accepted = await webhook_worker.enqueue(data, event_key)
    if not accepted:
        logger.info("Webhook event '%s' already accepted, ignoring retry", event_key)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "action": "duplicate_ignored"},
        )

    return {"status": "ok", "action": "accepted"}
