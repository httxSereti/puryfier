"""Payload tests for the Chaster extension lock actions."""

import asyncio
import json

import httpx

from utils import chaster_api


def install_client(monkeypatch, calls: list[httpx.Request]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json={"ok": True})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=chaster_api.CHASTER_BASE_URL,
    )
    monkeypatch.setattr(chaster_api, "chaster_client", client)


def action_payload(request: httpx.Request) -> dict:
    return json.loads(request.content)["action"]


def test_freeze_unfreeze_and_toggle_payloads(monkeypatch):
    calls: list[httpx.Request] = []
    install_client(monkeypatch, calls)

    assert asyncio.run(chaster_api.freeze_lock("session-1")) is True
    assert asyncio.run(chaster_api.unfreeze_lock("session-1")) is True
    assert asyncio.run(chaster_api.toggle_freeze_lock("session-1")) is True

    assert [action_payload(request) for request in calls] == [
        {"name": "freeze"},
        {"name": "unfreeze"},
        {"name": "toggle_freeze"},
    ]
    assert all(
        request.url.path == "/api/extensions/sessions/session-1/action"
        for request in calls
    )


def test_pillory_payload(monkeypatch):
    calls: list[httpx.Request] = []
    install_client(monkeypatch, calls)

    assert (
        asyncio.run(
            chaster_api.pillory_lock(
                "session-1", 300, reason="Censored media"
            )
        )
        is True
    )

    assert action_payload(calls[0]) == {
        "name": "pillory",
        "params": {"duration": 300, "reason": "Censored media"},
    }


def test_pillory_payload_without_reason(monkeypatch):
    calls: list[httpx.Request] = []
    install_client(monkeypatch, calls)

    assert asyncio.run(chaster_api.pillory_lock("session-1", 300)) is True
    assert action_payload(calls[0]) == {
        "name": "pillory",
        "params": {"duration": 300},
    }


def test_timer_visibility_payload(monkeypatch):
    calls: list[httpx.Request] = []
    install_client(monkeypatch, calls)

    assert (
        asyncio.run(
            chaster_api.set_display_remaining_time("session-1", False)
        )
        is True
    )
    assert action_payload(calls[0]) == {
        "name": "set_display_remaining_time",
        "params": False,
    }
