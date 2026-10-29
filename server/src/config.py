"""Typed application settings.

All environment access goes through this module. Secrets are wrapped in
``SecretStr`` so they cannot leak through ``repr()``, logs or error messages.
Values are loaded from the environment (and from a local ``.env`` file during
development) when the application is created; :meth:`Settings.validate_for_startup`
then fails fast when a critical setting is missing.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "mongodb://puryfi:puryfi@localhost:27017/puryfi_chaster?authSource=admin"
DEFAULT_FRONT_URL = "http://localhost:5173"
DEFAULT_LOG_LEVEL = "INFO"

WEBHOOK_USER_ENV = "CHASTER_WEBHOOK_USER"
WEBHOOK_PWD_ENV = "CHASTER_WEBHOOK_PWD"


class WebhookCredentialsNotConfigured(RuntimeError):
    """Raised when the Chaster webhook credentials are missing or blank."""


class Settings(BaseSettings):
    """Validated process settings, loaded once per application instance."""

    model_config = SettingsConfigDict(
        # Later files win. ``.env`` covers Docker/local runs from the repo
        # root; ``../.env`` keeps the monorepo root file working when uvicorn
        # is started from ``server/``.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    chaster_developer_token: SecretStr = Field(default_factory=lambda: SecretStr(""))
    chaster_webhook_user: SecretStr = Field(default_factory=lambda: SecretStr(""))
    chaster_webhook_pwd: SecretStr = Field(default_factory=lambda: SecretStr(""))

    database_url: str = DEFAULT_DATABASE_URL
    database_name: str | None = None

    front_url: str = DEFAULT_FRONT_URL

    log_level: str = DEFAULT_LOG_LEVEL
    log_format: Literal["json", "console"] | None = None

    # Reserved for encrypting link tokens and lock passwords at rest.
    secret_key: SecretStr = Field(default_factory=lambda: SecretStr(""))

    @field_validator("database_name", mode="before")
    @classmethod
    def _normalize_database_name(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("front_url")
    @classmethod
    def _normalize_front_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("FRONT_URL must be an absolute http(s) URL")
        return normalized

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> str:
        normalized = str(value or DEFAULT_LOG_LEVEL).strip().upper()
        if not normalized:
            return DEFAULT_LOG_LEVEL
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"Unknown LOG_LEVEL: {normalized}")
        return normalized

    @field_validator("log_format", mode="before")
    @classmethod
    def _normalize_log_format(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

    def webhook_credentials(self) -> tuple[str, str]:
        """Return the Basic-auth credentials, or fail closed.

        Empty credentials used to make ``Authorization: Basic Og==`` (empty
        user and password) valid. Both values are mandatory: we reject blank
        values instead of comparing against them.
        """
        user = self.chaster_webhook_user.get_secret_value().strip()
        password = self.chaster_webhook_pwd.get_secret_value().strip()

        if not user or not password:
            raise WebhookCredentialsNotConfigured(
                f"{WEBHOOK_USER_ENV} and {WEBHOOK_PWD_ENV} must both be set "
                "and non-empty; the Chaster webhook endpoint is disabled until "
                "they are configured."
            )

        return user, password

    def validate_for_startup(self) -> None:
        """Refuse to start when a critical setting is missing.

        The webhook credentials are checked first because accepting
        unauthenticated webhooks is the most dangerous failure mode.
        """
        self.webhook_credentials()

        if not self.database_url.strip():
            raise RuntimeError("DATABASE_URL must be set and non-empty")

        if not self.chaster_developer_token.get_secret_value().strip():
            raise RuntimeError(
                "CHASTER_DEVELOPER_TOKEN must be set and non-empty; "
                "Chaster API calls cannot be authenticated without it."
            )


@lru_cache
def get_settings() -> Settings:
    """Return the process settings (cached).

    The application factory builds one instance and stores it on
    ``app.state.settings``. The cache exists for small scripts and backward
    compatible helpers; tests that change the environment should construct a
    fresh :class:`Settings` instead.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings (used by tests and embedded apps)."""
    get_settings.cache_clear()


__all__ = [
    "DEFAULT_DATABASE_URL",
    "DEFAULT_FRONT_URL",
    "DEFAULT_LOG_LEVEL",
    "WEBHOOK_PWD_ENV",
    "WEBHOOK_USER_ENV",
    "Settings",
    "WebhookCredentialsNotConfigured",
    "clear_settings_cache",
    "get_settings",
]
