"""Tests for typed Settings and app.state dependency injection."""

import pytest

from config import Settings, WebhookCredentialsNotConfigured


class TestSettings:
    def test_secrets_are_masked_in_repr(self):
        settings = Settings(
            chaster_developer_token="developer-secret",
            chaster_webhook_user="webhook-user",
            chaster_webhook_pwd="webhook-secret",
        )

        rendered = repr(settings)
        assert "developer-secret" not in rendered
        assert "webhook-user" not in rendered
        assert "webhook-secret" not in rendered
        assert settings.chaster_developer_token.get_secret_value() == "developer-secret"

    def test_webhook_credentials_are_normalized_and_validated(self):
        settings = Settings(
            chaster_webhook_user="  user  ",
            chaster_webhook_pwd="  password  ",
        )

        assert settings.webhook_credentials() == ("user", "password")

    @pytest.mark.parametrize(
        ("user", "password"),
        [("", ""), ("   ", "   "), ("", "pwd"), ("user", "")],
        ids=["empty", "whitespace", "missing-user", "missing-password"],
    )
    def test_blank_webhook_credentials_fail_closed(self, user, password):
        settings = Settings(
            chaster_webhook_user=user,
            chaster_webhook_pwd=password,
        )

        with pytest.raises(WebhookCredentialsNotConfigured):
            settings.webhook_credentials()

    def test_startup_requires_a_chaster_developer_token(self):
        settings = Settings(
            chaster_developer_token="",
            chaster_webhook_user="user",
            chaster_webhook_pwd="password",
        )

        with pytest.raises(RuntimeError, match="CHASTER_DEVELOPER_TOKEN"):
            settings.validate_for_startup()

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("json", "json"), ("JSON", "json"), ("console", "console"), ("", None)],
    )
    def test_log_format_is_normalized(self, raw, expected):
        assert Settings(log_format=raw).log_format == expected

    def test_front_url_has_no_trailing_slash(self):
        assert Settings(front_url="https://example.com/").front_url == "https://example.com"


class TestAppStateDependencies:
    def test_settings_and_container_are_bound_to_the_app(self, client):
        settings = client.app.state.settings
        container = client.app.state.container

        assert container.settings is settings
        assert container.session_repository is not None
        assert container.message_queue is not None
        assert container.puryfi_registry is not None
        assert container.webhook_worker is not None

    def test_create_app_keeps_instances_isolated(self, client):
        from container import set_active_container
        from main import create_app

        other = create_app(Settings())
        try:
            assert other.state.settings is not client.app.state.settings
            assert other.state.container is not client.app.state.container
        finally:
            # Restore the active container for the running test app.
            set_active_container(client.app.state.container)
