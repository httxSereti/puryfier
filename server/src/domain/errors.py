"""Framework-free domain errors."""


class DomainError(Exception):
    """Base class for expected business errors."""


class SessionNotFoundError(DomainError):
    """No lock configuration exists for the requested Chaster session."""


class PermissionDeniedError(DomainError):
    """The Chaster role is not allowed to perform this action."""


class InvalidWebhookPayloadError(ValueError):
    """A webhook payload is missing the identity needed for idempotency."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
