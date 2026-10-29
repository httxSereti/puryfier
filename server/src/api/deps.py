"""API dependencies and webhook authentication."""

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config import (
    WEBHOOK_PWD_ENV,
    WEBHOOK_USER_ENV,
    Settings,
    WebhookCredentialsNotConfigured,
    get_settings,
)
from container import Container
from domain.ports import (
    ChasterGateway,
    LockSessionRepository,
    MessageQueue,
    PuryfiRegistry,
    SessionWatchers,
)
from infra.logging import get_logger
from workers.webhook_inbox import WebhookInboxWorker

log = get_logger(__name__)

security = HTTPBasic()

__all__ = [
    "WEBHOOK_PWD_ENV",
    "WEBHOOK_USER_ENV",
    "WebhookCredentialsNotConfigured",
    "get_chaster_gateway",
    "get_container",
    "get_message_queue",
    "get_puryfi_registry",
    "get_session_repository",
    "get_session_watchers",
    "get_webhook_credentials",
    "get_webhook_worker",
    "validate_webhook_credentials",
    "verify_credentials",
]


def get_webhook_credentials(settings: Settings | None = None) -> tuple[str, str]:
    """Return the configured webhook credentials, or fail closed."""
    return (settings or get_settings()).webhook_credentials()


def validate_webhook_credentials(settings: Settings | None = None) -> None:
    """Refuse to start the application when webhook auth is not configured."""
    try:
        get_webhook_credentials(settings)
    except WebhookCredentialsNotConfigured as exc:
        raise RuntimeError(str(exc)) from exc


def get_container(request: Request) -> Container:
    """Return the dependency container bound to the current application."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("Application container is not initialised")
    return container


def _request_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


def verify_credentials(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
):
    try:
        expected_user, expected_pwd = _request_settings(request).webhook_credentials()
    except WebhookCredentialsNotConfigured:
        # Defense in depth: even if startup validation is bypassed (tests,
        # embedded ASGI usage), never accept an unauthenticated webhook.
        log.error("webhook.credentials_missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook authentication is not configured",
        )

    correct_username = secrets.compare_digest(credentials.username.encode("utf8"), expected_user.encode("utf8"))
    correct_password = secrets.compare_digest(credentials.password.encode("utf8"), expected_pwd.encode("utf8"))
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_chaster_gateway(
    container: Container = Depends(get_container),
) -> ChasterGateway:
    return container.chaster_gateway


def get_session_repository(
    container: Container = Depends(get_container),
) -> LockSessionRepository:
    return container.session_repository


def get_message_queue(
    container: Container = Depends(get_container),
) -> MessageQueue:
    return container.message_queue


def get_puryfi_registry(
    container: Container = Depends(get_container),
) -> PuryfiRegistry:
    return container.puryfi_registry


def get_session_watchers(
    container: Container = Depends(get_container),
) -> SessionWatchers:
    return container.session_watchers


def get_webhook_worker(
    container: Container = Depends(get_container),
) -> WebhookInboxWorker:
    return container.webhook_worker
