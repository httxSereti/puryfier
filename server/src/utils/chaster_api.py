import asyncio
import os
import random

import httpx
from fastapi import HTTPException

from utils.logging_config import get_logger
from utils.redaction import redact_path

log = get_logger(__name__)

CHASTER_BASE_URL = "https://api.chaster.app"
CHASTER_MAX_ATTEMPTS = 3
CHASTER_RETRY_BASE_DELAY = 0.5
CHASTER_RETRY_MAX_DELAY = 5.0
CHASTER_RETRYABLE_STATUS_CODES = {408, 429}

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


def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), CHASTER_RETRY_MAX_DELAY)

    delay = min(
        CHASTER_RETRY_BASE_DELAY * (2 ** (attempt - 1)),
        CHASTER_RETRY_MAX_DELAY,
    )
    # Jitter avoids a thundering herd when several sessions retry together.
    return delay + random.uniform(0, 0.25)


async def request_chaster(method: str, path: str, **kwargs) -> httpx.Response:
    """Call Chaster with bounded exponential backoff.

    Retries transport errors, 408/429 and 5xx responses. Client errors (401,
    404, 422, ...) are returned immediately to the caller.
    """
    for attempt in range(1, CHASTER_MAX_ATTEMPTS + 1):
        try:
            response = await chaster_client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            if attempt >= CHASTER_MAX_ATTEMPTS:
                log.error(
                    "chaster.request_failed",
                    chaster_method=method,
                    chaster_path=redact_path(path),
                    chaster_attempt=attempt,
                    chaster_error=type(exc).__name__,
                )
                raise

            delay = _retry_delay(attempt)
            log.warning(
                "chaster.request_retry",
                chaster_method=method,
                chaster_path=redact_path(path),
                chaster_attempt=attempt,
                chaster_error=type(exc).__name__,
                retry_in=round(delay, 3),
            )
            await asyncio.sleep(delay)
            continue

        retryable_status = (
            response.status_code in CHASTER_RETRYABLE_STATUS_CODES
            or 500 <= response.status_code < 600
        )
        if not retryable_status:
            return response

        if attempt >= CHASTER_MAX_ATTEMPTS:
            log.error(
                "chaster.request_failed",
                chaster_method=method,
                chaster_path=redact_path(path),
                chaster_attempt=attempt,
                chaster_status=response.status_code,
            )
            return response

        delay = _retry_delay(attempt, response)
        log.warning(
            "chaster.request_retry",
            chaster_method=method,
            chaster_path=redact_path(path),
            chaster_attempt=attempt,
            chaster_status=response.status_code,
            retry_in=round(delay, 3),
        )
        await asyncio.sleep(delay)

    # The loop always returns/raises; this is only here for type checkers.
    raise RuntimeError("Chaster retry loop exited unexpectedly")


async def get_session_auth(main_token: str) -> dict:
    """
    GET /api/extensions/auth/sessions/{main_token}

    Returns the parsed Chaster session payload. Raises HTTPException with the
    upstream status code on failure.
    """
    try:
        response = await request_chaster(
            "GET", f"/api/extensions/auth/sessions/{main_token}"
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        # Never expose str(e): httpx includes the request URL, which contains
        # the secret main_token.
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Chaster rejected the session token",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502, detail="Chaster API is unavailable"
        ) from e


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
        response = await request_chaster(
            "POST",
            f"/api/extensions/sessions/{session_id}/logs/custom",
            json=payload,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        log.warning(
            "chaster.custom_log_failed",
            chaster_session_id=session_id,
            exc_info=True,
        )
        return False
