"""Tests for Chaster API retries and structured retry logs (REVIEW.md P1 #7)."""

import asyncio
import logging

import httpx
import pytest
from fastapi import HTTPException

from services.chaster import add_time_to_lock
from utils import chaster_api


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(chaster_api, "CHASTER_RETRY_BASE_DELAY", 0)
    monkeypatch.setattr(chaster_api, "CHASTER_RETRY_MAX_DELAY", 0)
    monkeypatch.setattr(chaster_api.random, "uniform", lambda _a, _b: 0)


def install_client(monkeypatch, handler) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=chaster_api.CHASTER_BASE_URL,
    )
    monkeypatch.setattr(chaster_api, "chaster_client", client)


class TestRetryPolicy:
    def test_retries_5xx_then_succeeds(self, monkeypatch):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(500, json={"detail": "temporary"})
            return httpx.Response(200, json={"role": "wearer"})

        install_client(monkeypatch, handler)

        result = asyncio.run(chaster_api.get_session_auth("secret-main-token"))

        assert result == {"role": "wearer"}
        assert len(calls) == 2

    def test_retries_transport_error_then_succeeds(self, monkeypatch):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ConnectError("network down", request=request)
            return httpx.Response(200, json={"role": "wearer"})

        install_client(monkeypatch, handler)

        result = asyncio.run(chaster_api.get_session_auth("secret-main-token"))

        assert result == {"role": "wearer"}
        assert len(calls) == 2

    def test_does_not_retry_4xx(self, monkeypatch):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(401, json={"detail": "unauthorized"})

        install_client(monkeypatch, handler)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(chaster_api.get_session_auth("secret-main-token"))

        assert exc_info.value.status_code == 401
        assert len(calls) == 1

    def test_gives_up_after_max_attempts(self, monkeypatch):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(503, json={"detail": "down"})

        install_client(monkeypatch, handler)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(chaster_api.get_session_auth("secret-main-token"))

        assert exc_info.value.status_code == 503
        assert len(calls) == chaster_api.CHASTER_MAX_ATTEMPTS

    def test_add_time_is_retried(self, monkeypatch):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(502)
            return httpx.Response(201, json={"ok": True})

        install_client(monkeypatch, handler)

        assert asyncio.run(add_time_to_lock("session-1", 600)) is True
        assert len(calls) == 2


class TestRetryLogs:
    def test_retry_log_is_structured_and_does_not_leak_token(
        self, monkeypatch, caplog
    ):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(500)
            return httpx.Response(200, json={"role": "wearer"})

        install_client(monkeypatch, handler)

        with caplog.at_level(logging.WARNING, logger="utils.chaster_api"):
            asyncio.run(chaster_api.get_session_auth("super-secret-token"))

        retry_record = next(
            record
            for record in caplog.records
            if isinstance(record.msg, dict)
            and record.msg.get("event") == "chaster.request_retry"
        )
        fields = retry_record.msg
        assert retry_record.levelname == "WARNING"
        assert fields["chaster_method"] == "GET"
        assert fields["chaster_attempt"] == 1
        assert fields["chaster_status"] == 500
        assert "super-secret-token" not in fields["chaster_path"]
        assert "<token:" in fields["chaster_path"]
