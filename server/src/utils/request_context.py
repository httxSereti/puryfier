"""Attach a request id and request metadata to every log line.

The middleware works for HTTP and WebSocket connections. Paths are redacted
before being bound, because they can contain Chaster session/link tokens.
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from utils.logging_config import get_logger
from utils.redaction import redact_path

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = get_logger(__name__)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)

        structlog.contextvars.clear_contextvars()
        context: dict[str, object] = {
            "request_id": request_id,
            "path": redact_path(scope.get("path", "")),
        }
        if scope["type"] == "http":
            context["method"] = scope.get("method")
        structlog.contextvars.bind_contextvars(**context)

        started = time.perf_counter()
        status_code: int | None = None
        close_code: int | None = None

        async def send_with_context(message: Message) -> None:
            nonlocal status_code, close_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            elif message["type"] == "websocket.close":
                close_code = message.get("code")
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            if scope["type"] == "http":
                log.exception(
                    "http.request_failed",
                    duration_ms=_elapsed_ms(started),
                )
            raise
        else:
            if scope["type"] == "http":
                log.info(
                    "http.request",
                    status_code=status_code,
                    duration_ms=_elapsed_ms(started),
                )
            else:
                log.debug(
                    "websocket.closed",
                    close_code=close_code,
                    duration_ms=_elapsed_ms(started),
                )
        finally:
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _request_id(scope: Scope) -> str:
        supplied = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        if _VALID_REQUEST_ID.fullmatch(supplied):
            return supplied
        return uuid.uuid4().hex[:12]


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


__all__ = ["REQUEST_ID_HEADER", "RequestContextMiddleware"]
