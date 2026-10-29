"""API dependencies and webhook authentication."""

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import container
from domain.ports import (
    ChasterGateway,
    LockSessionRepository,
    MessageQueue,
    PuryfiRegistry,
    SessionWatchers,
)
from infra.logging import get_logger

log = get_logger(__name__)

security = HTTPBasic()

WEBHOOK_USER_ENV = "CHASTER_WEBHOOK_USER"
WEBHOOK_PWD_ENV = "CHASTER_WEBHOOK_PWD"


class WebhookCredentialsNotConfigured(RuntimeError):
    """Raised when the Chaster webhook credentials are missing or blank."""


def get_webhook_credentials() -> tuple[str, str]:
    """Return the configured webhook credentials, or fail closed.

    Empty credentials used to make ``Authorization: Basic Og==`` (empty user
    and password) valid. Both values are now mandatory: we reject blank values
    instead of comparing against them.
    """
    expected_user = os.getenv(WEBHOOK_USER_ENV, "")
    expected_pwd = os.getenv(WEBHOOK_PWD_ENV, "")

    if not expected_user.strip() or not expected_pwd.strip():
        raise WebhookCredentialsNotConfigured(
            f"{WEBHOOK_USER_ENV} and {WEBHOOK_PWD_ENV} must both be set and non-empty; "
            "the Chaster webhook endpoint is disabled until they are configured."
        )

    return expected_user, expected_pwd


def validate_webhook_credentials() -> None:
    """Refuse to start the application when webhook auth is not configured."""
    try:
        get_webhook_credentials()
    except WebhookCredentialsNotConfigured as exc:
        raise RuntimeError(str(exc)) from exc


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    try:
        expected_user, expected_pwd = get_webhook_credentials()
    except WebhookCredentialsNotConfigured:
        # Defense in depth: even if startup validation is bypassed (tests,
        # embedded ASGI usage), never accept an unauthenticated webhook.
        log.error("webhook.credentials_missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook authentication is not configured",
        )

    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"), expected_user.encode("utf8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"), expected_pwd.encode("utf8")
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_chaster_gateway() -> ChasterGateway:
    return container.chaster_gateway


def get_session_repository() -> LockSessionRepository:
    return container.session_repository


def get_message_queue() -> MessageQueue:
    return container.message_queue


def get_puryfi_registry() -> PuryfiRegistry:
    return container.puryfi_registry


def get_session_watchers() -> SessionWatchers:
    return container.session_watchers
