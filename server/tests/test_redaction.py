"""Tests for token redaction in logs and paths (REVIEW.md critical #7)."""

import logging

import pytest

from utils.redaction import (
    AccessLogTokenFilter,
    install_access_log_redaction,
    redact_path,
    token_fingerprint,
)


class TestTokenFingerprint:
    def test_is_stable_and_does_not_contain_the_token(self):
        token = "super-secret-token"
        first = token_fingerprint(token)

        assert first == token_fingerprint(token)
        assert token not in first
        assert first.startswith("<token:")

    def test_different_tokens_have_different_fingerprints(self):
        assert token_fingerprint("token-a") != token_fingerprint("token-b")

    def test_none_is_explicit(self):
        assert token_fingerprint(None) == "<none>"


class TestRedactPath:
    @pytest.mark.parametrize(
        ("path", "prefix", "suffix"),
        [
            ("/api/session/secret-main", "/api/session/", ""),
            (
                "/api/session/secret-main/link-token",
                "/api/session/",
                "/link-token",
            ),
            ("/api/configuration/secret-config", "/api/configuration/", ""),
            ("/ws/session/secret-main", "/ws/session/", ""),
            ("/ws/configuration/secret-config", "/ws/configuration/", ""),
            ("/ws/secret-link", "/ws/", ""),
        ],
    )
    def test_token_segments_are_fingerprinted(self, path, prefix, suffix):
        redacted = redact_path(path)

        assert "secret-" not in redacted
        assert redacted.startswith(prefix)
        assert redacted.endswith(suffix)

    def test_non_token_paths_are_unchanged(self):
        path = "/api/webhooks/extensions/chaster"
        assert redact_path(path) == path

    def test_redaction_is_idempotent(self):
        path = "/api/session/secret-main"
        once = redact_path(path)

        assert redact_path(once) == once

    def test_chaster_upstream_urls_are_redacted(self):
        url = "https://api.chaster.app/api/extensions/auth/sessions/secret-main"

        redacted = redact_path(url)

        assert "secret-main" not in redacted
        assert "/api/extensions/auth/sessions/<token:" in redacted


class TestAccessLogTokenFilter:
    def test_install_is_idempotent(self):
        logger = logging.getLogger("uvicorn.access")

        install_access_log_redaction()
        install_access_log_redaction()

        assert sum(
            isinstance(entry, AccessLogTokenFilter) for entry in logger.filters
        ) == 1

    def test_http_access_log_path_is_redacted(self):
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1:1234", "GET", "/api/session/secret-main", "1.1", 200),
            exc_info=None,
        )

        AccessLogTokenFilter().filter(record)
        rendered = record.getMessage()

        assert "secret-main" not in rendered
        assert token_fingerprint("secret-main") in rendered

    def test_websocket_access_log_path_is_redacted(self):
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='%s - "WebSocket %s" %d',
            args=("127.0.0.1:1234", "/ws/secret-link", 101),
            exc_info=None,
        )

        AccessLogTokenFilter().filter(record)
        rendered = record.getMessage()

        assert "secret-link" not in rendered
        assert token_fingerprint("secret-link") in rendered
