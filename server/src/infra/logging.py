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

from config import Settings

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


def _log_level(settings: Settings) -> int:
    levels = logging.getLevelNamesMapping()
    return levels.get(settings.log_level.upper(), logging.INFO)


def _use_json(settings: Settings) -> bool:
    if settings.log_format is not None:
        return settings.log_format == "json"
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


def configure_logging(settings: Settings | None = None, *, force: bool = False) -> None:
    """Configure structlog and route every stdlib logger through it.

    Settings are supplied by the application factory so log level and format
    follow the same typed configuration as the rest of the process. The
    function is idempotent unless ``force`` is set (used when a new app
    instance replaces the module-level one in tests).
    """
    global _configured
    if _configured and not force:
        return

    settings = settings or Settings()
    use_json = _use_json(settings)
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
    root.setLevel(_log_level(settings))

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
