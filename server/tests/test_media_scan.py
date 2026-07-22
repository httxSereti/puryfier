"""Tests for staticMediaScan counting (REVIEW.md #11).

The "add time when a media is censored" feature must count censored *images*:
one scan message == one image, and it only counts when a censorable label was
detected. A detected face or hand must NOT add time.
"""

import asyncio

import msgpack
import pytest

import models.connection as connection_module
from models.connection import Connection
from typings.puryfi_enums import PuryfiObjectLabel


class FakeWebSocket:
    async def send_bytes(self, data: bytes):
        pass


class FakeLockConfig:
    link_token = "tok"
    session_id = "session-1"
    has_linked_plugin = True

    class config:
        class censorPicsConfig:
            enabled = True
            limit_count = 2
            added_duration = 600


def make_connection() -> Connection:
    conn = Connection(FakeWebSocket(), FakeLockConfig())
    conn.user_lock_config = FakeLockConfig()
    return conn


def scan_message(labels: list[int]) -> bytes:
    return msgpack.packb({
        "type": "staticMediaScan",
        "payload": {"objects": [{"label": label} for label in labels]},
    })


@pytest.fixture()
def mock_add_time(monkeypatch):
    calls: list[tuple[str, int]] = []

    async def fake_add_time(session_id: str, duration: int) -> bool:
        calls.append((session_id, duration))
        return True

    async def fake_log(*args, **kwargs) -> bool:
        return True

    monkeypatch.setattr(connection_module, "add_time_to_lock", fake_add_time)
    monkeypatch.setattr(connection_module, "create_custom_log", fake_log)
    return calls


class TestMediaScanCounting:
    def test_face_and_hand_do_not_count(self, mock_add_time):
        conn = make_connection()

        asyncio.run(conn.handle_message(scan_message([
            PuryfiObjectLabel.FemaleFace, PuryfiObjectLabel.Hand,
        ])))

        assert conn.seen_censored_objects == 0
        assert mock_add_time == []

    def test_censorable_label_counts_once_per_scan(self, mock_add_time):
        conn = make_connection()

        # Multiple censorable objects in ONE image still count as one image.
        asyncio.run(conn.handle_message(scan_message([
            PuryfiObjectLabel.FemaleBreast, PuryfiObjectLabel.Buttocks,
        ])))

        assert conn.seen_censored_objects == 1
        assert mock_add_time == []  # limit is 2, not reached yet

    def test_time_added_when_limit_reached(self, mock_add_time):
        conn = make_connection()

        asyncio.run(conn.handle_message(scan_message([PuryfiObjectLabel.Buttocks])))
        asyncio.run(conn.handle_message(scan_message([PuryfiObjectLabel.Anus])))

        assert mock_add_time == [("session-1", 600)]
        assert conn.seen_censored_objects == 0  # counter reset after adding time

    def test_mixed_scan_counts_only_when_censorable(self, mock_add_time):
        conn = make_connection()

        asyncio.run(conn.handle_message(scan_message([
            PuryfiObjectLabel.FemaleFace, PuryfiObjectLabel.FemaleGenitals,
        ])))

        assert conn.seen_censored_objects == 1

    def test_disabled_feature_counts_nothing(self, mock_add_time, monkeypatch):
        conn = make_connection()

        class DisabledConfig:
            class censorPicsConfig:
                enabled = False
                limit_count = 1
                added_duration = 600

        conn.user_lock_config.config = DisabledConfig

        asyncio.run(conn.handle_message(scan_message([PuryfiObjectLabel.Buttocks])))

        assert conn.seen_censored_objects == 0
        assert mock_add_time == []
