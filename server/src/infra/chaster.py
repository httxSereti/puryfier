import asyncio
import random
from typing import Any

import httpx
from fastapi import HTTPException

from config import Settings
from domain.entities import (
    ChasterConfiguration,
    ChasterExtensionConfigSchema,
    ChasterSessionAuth,
)
from infra.logging import get_logger
from infra.redaction import redact_path

log = get_logger(__name__)

CHASTER_BASE_URL = "https://api.chaster.app"
CHASTER_MAX_ATTEMPTS = 3
CHASTER_RETRY_BASE_DELAY = 0.5
CHASTER_RETRY_MAX_DELAY = 5.0
CHASTER_RETRYABLE_STATUS_CODES = {408, 429}

# Shared async client for all Chaster API calls (see REVIEW.md #4).
# It is created at application startup from typed settings, never at import
# time, so no token is captured when a module is merely imported. Always
# access it via the module (`chaster_api.chaster_client`) so tests can swap it
# with a mock-transport client.
chaster_client: httpx.AsyncClient | None = None


def configure_chaster_client(settings: Settings) -> httpx.AsyncClient:
    """Build the process-wide Chaster client from validated settings."""
    global chaster_client

    chaster_client = httpx.AsyncClient(
        base_url=CHASTER_BASE_URL,
        headers={
            "accept": "application/json",
            "Authorization": f"Bearer {settings.chaster_developer_token.get_secret_value()}",
        },
        timeout=10.0,
    )
    return chaster_client


async def close_chaster_client() -> None:
    """Close the shared client (called from the app lifespan shutdown)."""
    global chaster_client

    client = chaster_client
    chaster_client = None
    if client is None:
        return

    close = getattr(client, "aclose", None)
    if close is not None:
        await close()


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
        client = chaster_client
        if client is None:
            raise RuntimeError(
                "Chaster client is not configured; call configure_chaster_client() first"
            )

        try:
            response = await client.request(method, path, **kwargs)
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


async def create_custom_log(
    session_id: str,
    title: str,
    description: str,
    role: str,
    icon: str = "link",
    color: str = "#ffffff",
) -> bool:
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


async def add_time_to_lock(session_id: str, duration: int) -> bool:
    """Add ``duration`` seconds to a Chaster lock."""
    try:
        response = await request_chaster(
            "POST",
            f"/api/extensions/sessions/{session_id}/action",
            json={"action": {"name": "add_time", "params": duration}},
        )
        return response.status_code == 201
    except httpx.HTTPError:
        log.warning(
            "chaster.add_time_failed",
            chaster_session_id=session_id,
            duration=duration,
            exc_info=True,
        )
        return False


async def get_configuration(configuration_token: str) -> dict:
    """GET /api/extensions/configurations/{configuration_token}."""
    response = await request_chaster(
        "GET", f"/api/extensions/configurations/{configuration_token}"
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise TypeError("Unexpected Chaster response")
    return data


async def update_configuration(
    configuration_token: str, config: "ChasterExtensionConfigSchema"
) -> str | None:
    """Persist an extension configuration in Chaster.

    Returns the Chaster session id when the response carries one. The caller
    keeps the validated local payload as the source of truth.
    """
    response = await request_chaster(
        "PUT",
        f"/api/extensions/configurations/{configuration_token}",
        json={"config": config.model_dump()},
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise TypeError("Unexpected Chaster response")

    session_id = data.get("sessionId")
    # Not logging the full Chaster response: it contains user data.
    log.info("configuration.session_resolved", session_id=session_id)
    return session_id if isinstance(session_id, str) and session_id else None


def parse_session_auth(data: dict) -> ChasterSessionAuth:
    raw_session = data.get("session")
    session: dict[str, Any] = raw_session if isinstance(raw_session, dict) else {}
    raw_lock = session.get("lock")
    lock: dict[str, Any] = raw_lock if isinstance(raw_lock, dict) else {}
    keyholder = lock.get("keyholder")
    wearer = lock.get("user")

    return ChasterSessionAuth(
        role=data.get("role", ""),
        session_id=session.get("sessionId", ""),
        lock_id=lock.get("_id") or None,
        keyholder_id=keyholder.get("_id") if isinstance(keyholder, dict) else None,
        wearer_id=wearer.get("_id") if isinstance(wearer, dict) else None,
        config=session.get("config") or {},
    )


def parse_configuration(data: dict) -> ChasterConfiguration:
    config = data.get("config")
    session_id = data.get("sessionId")
    return ChasterConfiguration(
        role=data.get("role", ""),
        session_id=session_id if isinstance(session_id, str) and session_id else None,
        config=config if isinstance(config, dict) else {},
    )


class ChasterService:
    """Adapter implementing the domain ``ChasterGateway`` port."""

    async def get_session_auth(self, main_token: str) -> ChasterSessionAuth:
        return parse_session_auth(await get_session_auth(main_token))

    async def get_configuration(
        self, configuration_token: str
    ) -> ChasterConfiguration:
        return parse_configuration(await get_configuration(configuration_token))

    async def update_configuration(
        self,
        configuration_token: str,
        config: "ChasterExtensionConfigSchema",
    ) -> str | None:
        return await update_configuration(configuration_token, config)

    async def add_time(self, session_id: str, duration: int) -> bool:
        return await add_time_to_lock(session_id, duration)

    async def create_log(
        self,
        session_id: str,
        *,
        role: str,
        title: str,
        description: str,
        icon: str = "link",
        color: str = "#ffffff",
    ) -> bool:
        return await create_custom_log(
            session_id,
            title=title,
            description=description,
            role=role,
            icon=icon,
            color=color,
        )
