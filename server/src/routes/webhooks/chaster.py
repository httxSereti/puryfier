from fastapi import APIRouter
from models.connection_manager import manager
from models.documents import ProcessedWebhookEvent
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from fastapi import status, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError
from .actions import handle_lock_frozen, handle_lock_unfrozen, handle_extension_updated
import json
import os
import secrets
from pprint import pprint

router = APIRouter(prefix="/api/webhooks", tags=["webhook"])
security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.getenv("CHASTER_WEBHOOK_USER", "")
    expected_pwd = os.getenv("CHASTER_WEBHOOK_PWD", "")

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


@router.post("/extensions/chaster")
async def chaster_webhook(request: Request, _: str = Depends(verify_credentials)):
    """
    Chaster webhook endpoint
    """
    print("----- PAYLOAD -----")
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON",
        )
    pprint(data)

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

    print(f"event '{event}'")
    print(f"requestId '{request_id}'")
    print("-------------")

    if event == "action_log.created":
        event_data = data.get("data")
        action_payload = event_data.get("actionLog") if isinstance(event_data, dict) else None
        action_type = action_payload.get("type") if isinstance(action_payload, dict) else None

        if not action_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required key: 'data.actionLog.type'",
            )

        print(f"actionType '{action_type}'")

    # Claim the requestId so that Chaster retries of an already-processed
    # webhook become no-ops (the unique index makes the first insert win).
    try:
        await ProcessedWebhookEvent(request_id=request_id).insert()
    except DuplicateKeyError:
        print(f"requestId '{request_id}' already processed, ignoring retry")
        return {"status": "ok", "action": "duplicate_ignored"}

    try:
        if event == "action_log.created":
            if action_type == "lock_frozen":
                return await handle_lock_frozen(data)

            if action_type == "lock_unfrozen":
                return await handle_lock_unfrozen(data)

            if action_type == "extension_updated":
                return await handle_extension_updated(data)

        return {"status": "ok"}
    except Exception:
        # Processing failed: release the claim so Chaster's retry can reprocess.
        await ProcessedWebhookEvent.find_one(
            ProcessedWebhookEvent.request_id == request_id
        ).delete()
        raise
