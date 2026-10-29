"""Central structlog configuration.

The whole application logs through structlog, including standard-library
loggers (uvicorn, httpx, ...). Two renderers are supported:

* ``console``: coloured, human-readable output for development.
* ``json``: one JSON object per line, ready for Docker/production log
  collectors.

``LOG_FORMAT`` selects the renderer explicitly. When it is not set, logs are
JSON when stdout is not a TTY (Docker, systemd) and console otherwise.
"""

import logging
import os
import sys
from datetime import UTC, datetime

import structlog

DEFAULT_LOG_LEVEL = "INFO"
_configured = False


def _make_timestamp(include_milliseconds: bool) -> structlog.types.Processor:
    """Build a timestamp processor for the selected output format.

    Console logs only need seconds to stay readable. JSON keeps milliseconds
    so production logs can still be correlated precisely.
    """

    def add_timestamp(
        logger: structlog.types.WrappedLogger,
        method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        now = datetime.now(UTC)
        if include_milliseconds:
            formatted = now.isoformat(timespec="milliseconds")
        else:
            formatted = now.isoformat(timespec="seconds")
        event_dict["timestamp"] = formatted.replace("+00:00", "Z")
        return event_dict

    return add_timestamp


def _log_level() -> int:
    value = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    levels = logging.getLevelNamesMapping()
    return levels.get(value, logging.INFO)


def _use_json() -> bool:
    value = os.getenv("LOG_FORMAT", "").strip().lower()
    if value in {"json", "console"}:
        return value == "json"
    return not sys.stdout.isatty()


def _renderer(use_json: bool) -> structlog.types.Processor:
    if use_json:
        # ``default=str`` keeps the logger from crashing on ObjectId and
        # other non-JSON-native values.
        return structlog.processors.JSONRenderer(default=str, sort_keys=True)

    colors = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    return structlog.dev.ConsoleRenderer(colors=colors, sort_keys=False)


def _shared_processors(
    include_milliseconds: bool,
) -> list[structlog.types.Processor]:
    """Processors applied to structlog *and* standard-library records."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _make_timestamp(include_milliseconds),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def configure_logging() -> None:
    """Configure structlog and route every stdlib logger through it.

    Idempotent: uvicorn may import the app once, and tests may re-use it.
    """
    global _configured
    if _configured:
        return

    use_json = _use_json()
    shared_processors = _shared_processors(
        include_milliseconds=use_json,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _renderer(use_json),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_log_level())

    # Uvicorn installs its own handlers when it starts. Drop them so its
    # records bubble up to the root handler and share the same format.
    # Access lines are emitted by RequestContextMiddleware instead, with a
    # request id, duration and without the token-bearing URL.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    # HTTP client logs contain full request URLs (including Chaster tokens)
    # at INFO level: never let them through. Mongo/Beanie are too chatty.
    for name in ("httpx", "httpcore", "pymongo", "beanie"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for ``name``."""
    return structlog.get_logger(name)


__all__ = ["configure_logging", "get_logger"]
