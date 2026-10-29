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
from infra.logging import get_logger

log = get_logger(__name__)

log.info("connection.established", session_id=session_id, link_token=token_fingerprint(token))
log.warning("chaster.request_retry", attempt=2, retry_in=1.5)
log.exception("webhook.handler_failed", event_key=event_key)
```

Use `domain.action` event names and keep variable data in fields rather than
interpolating it into the event string.

## Code layout

The backend follows a layered layout (see `ARCHITECTURE_REVIEW.md`):

| Directory   | Responsibility                                                        |
| ----------- | --------------------------------------------------------------------- |
| `api/`      | HTTP and WebSocket transport; routes delegate to use cases.           |
| `domain/`   | Entities, events, ports and use cases. No FastAPI/Beanie/msgpack.     |
| `infra/`    | Chaster client, MongoDB documents/repositories, logging and redaction.|
| `realtime/` | Puryfi protocol, connection actor, registry and browser watchers.     |
| `workers/`  | Durable webhook inbox and outbound queue drain.                       |
| `container.py` | Process-wide composition root used until DI moves to `app.state`.  |

Historical import paths (`models/`, `routes/`, `services/`, `schemas/`,
`typings/`, `utils/`, `db.py`) are thin compatibility aliases for one release.
New code must import from the layered paths above.
