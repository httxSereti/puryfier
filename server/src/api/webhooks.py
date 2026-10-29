"""Chaster webhook ingress: authenticate, deduplicate, enqueue durably."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from api.deps import verify_credentials
from domain.errors import InvalidWebhookPayloadError
from domain.events import build_event_key
from infra.logging import get_logger
from workers.webhook_inbox import webhook_worker

log = get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhook"])


@router.post("/extensions/chaster", status_code=status.HTTP_202_ACCEPTED)
async def chaster_webhook(request: Request, _: str = Depends(verify_credentials)):
    """Accept a Chaster webhook and store it in the durable inbox.

    Processing (and any slow Puryfi RPC) happens in the background worker, so
    Chaster's 10s timeout is never hit.
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
    try:
        event_key = build_event_key(data)
    except InvalidWebhookPayloadError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.detail,
        ) from e

    if event_key is None:
        # Unknown event without a stable business identity: nothing stateful
        # to process, so acknowledge it without writing an inbox entry.
        return {"status": "ok", "action": "ignored_no_event_key"}

    accepted = await webhook_worker.enqueue(data, event_key)
    if not accepted:
        log.info("webhook.duplicate_ignored", event_key=event_key)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "action": "duplicate_ignored"},
        )

    return {"status": "ok", "action": "accepted"}