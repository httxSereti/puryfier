import logging
import re
from urllib.parse import unquote

from domain.redaction import token_fingerprint

_TOKEN_PATH_PATTERNS = (
    re.compile(r"(/api/session/)([^/?#]+)"),
    re.compile(r"(/api/configuration/)([^/?#]+)"),
    re.compile(r"(/api/extensions/auth/sessions/)([^/?#]+)"),
    re.compile(r"(/api/extensions/configurations/)([^/?#]+)"),
    re.compile(r"(/ws/session/)([^/?#]+)"),
    re.compile(r"(/ws/configuration/)([^/?#]+)"),
    re.compile(r"(/ws/)([^/?#]+)(?=[?#]|$)"),
)


def _redact_match(match: re.Match[str]) -> str:
    segment = match.group(2)
    if segment.startswith("<token:") and segment.endswith(">"):
        return match.group(0)
    return match.group(1) + token_fingerprint(unquote(segment))


def redact_path(path: str) -> str:
    """Replace secret path segments in an HTTP/WebSocket path with fingerprints."""
    redacted = path
    for pattern in _TOKEN_PATH_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


class AccessLogTokenFilter(logging.Filter):
    """Mask tokens in uvicorn access-log paths.

    Uvicorn logs the raw request path, so `/api/session/<token>` and
    `/ws/<link_token>` would otherwise leak secrets into stdout.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(
                redact_path(arg) if isinstance(arg, str) else arg for arg in args
            )
        elif isinstance(args, dict):
            record.args = {
                key: redact_path(value) if isinstance(value, str) else value
                for key, value in args.items()
            }
        return True


def install_access_log_redaction() -> None:
    """Install the access-log filter once, without duplicating it on reloads."""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(entry, AccessLogTokenFilter) for entry in access_logger.filters):
        access_logger.addFilter(AccessLogTokenFilter())
