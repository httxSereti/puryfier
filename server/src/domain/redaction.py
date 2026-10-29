"""Pure, framework-free redaction helpers used by the domain layer."""

import hashlib


def token_fingerprint(token: str | None) -> str:
    """Return a stable, non-reversible identifier for a secret token."""
    if not token:
        return "<none>"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return f"<token:{digest}>"
