# Backend using WebSocket

Backend for Puryfi plugin to link Chaster & Puryfi

## Logging

The server logs through [structlog](https://www.structlog.org/). Every log is
an event name plus structured key/value fields, and standard-library logs
(uvicorn, FastAPI, httpx, ...) use the same output.

| Variable     | Default                              | Description                                      |
| ------------ | ------------------------------------ | ------------------------------------------------ |
| `LOG_LEVEL`  | `INFO`                               | `DEBUG`, `INFO`, `WARNING`, `ERROR`, ...          |
| `LOG_FORMAT` | auto (`json` when stdout is not TTY) | `json` for production, `console` for development |
| `NO_COLOR`   | unset                                | Disable ANSI colours in `console` mode           |

HTTP and WebSocket requests get a `request_id` (returned in the `X-Request-ID`
response header). Sensitive path segments are replaced by token fingerprints
before being logged.

Usage:

```python
from utils.logging_config import get_logger

log = get_logger(__name__)

log.info("connection.established", session_id=session_id, link_token=token_fingerprint(token))
log.warning("chaster.request_retry", attempt=2, retry_in=1.5)
log.exception("webhook.handler_failed", event_key=event_key)
```

Use `domain.action` event names and keep variable data in fields rather than
interpolating it into the event string.
