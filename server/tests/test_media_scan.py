"""Tests for batched staticMediaScan counting.

PuryFi can emit many scans per second for one browsing user. The worker must
count every censorable image without doing I/O in the WebSocket read loop, and
must flush one aggregated batch per session window.
"""

import asyncio
from typing import Any

import msgpack

from domain.use_cases.media_scan import MediaScanService
from infra.repositories import MongoLockSessionRepository
from models.connection import Connection
from typings.puryfi_enums import PuryfiObjectLabel
from workers.media_scans import MediaScanBatcher


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


class RecordingSink:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def record_nowait(self, session, objects) -> None:
        self.calls.append((session, objects))


class FakeChaster:
    def __init__(self, outcomes: list[bool] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.add_time_calls: list[tuple[str, int]] = []
        self.log_calls: list[tuple[str, dict[str, Any]]] = []

    async def add_time(self, session_id: str, duration: int) -> bool:
        self.add_time_calls.append((session_id, duration))
        return self.outcomes.pop(0) if self.outcomes else True

    async def create_log(self, session_id: str, **kwargs: Any) -> bool:
        self.log_calls.append((session_id, kwargs))
        return True


def enabled_config(*, limit_count: int = 2, added_duration: int = 600) -> dict:
    return {
        "lock_on_freeze": True,
        "unlock_on_unfreeze": True,
        "censorPicsConfig": {
            "limit_count": limit_count,
            "added_duration": added_duration,
            "enabled": True,
        },
    }


def scan_message(labels: list[int]) -> bytes:
    return msgpack.packb({
        "type": "staticMediaScan",
        "payload": {"objects": [{"label": label} for label in labels]},
    })


def make_batcher(chaster: FakeChaster, *, window_seconds: float = 0.05) -> MediaScanBatcher:
    return MediaScanBatcher(
        scans=MediaScanService(
            sessions=MongoLockSessionRepository(),
            chaster=chaster,
        ),
        window_seconds=window_seconds,
        poll_seconds=0.005,
        retry_seconds=0.01,
    )


async def load_session(session_id: str):
    session = await MongoLockSessionRepository().get_by_session_id(session_id)
    assert session is not None
    return session


def stored_count(mongo_db, session_id: str) -> int:
    document = mongo_db["users_lock_configurations"].find_one(
        {"session_id": session_id}
    )
    assert document is not None
    return document["seen_censored_objects"]


class TestMediaScanBatching:
    def test_face_and_hand_do_not_count(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="face-session",
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster)
            session = await load_session("face-session")
            batcher.record_nowait(
                session,
                [
                    {"label": PuryfiObjectLabel.FemaleFace},
                    {"label": PuryfiObjectLabel.Hand},
                ],
            )
            await batcher.flush_all()

        asyncio.run(scenario())

        assert stored_count(mongo_db, "face-session") == 0
        assert chaster.add_time_calls == []

    def test_one_scan_with_many_objects_counts_once(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="one-image-session",
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster)
            session = await load_session("one-image-session")
            batcher.record_nowait(
                session,
                [
                    {"label": PuryfiObjectLabel.FemaleBreast},
                    {"label": PuryfiObjectLabel.Buttocks},
                ],
            )
            await batcher.flush_all()

        asyncio.run(scenario())

        assert stored_count(mongo_db, "one-image-session") == 1
        assert chaster.add_time_calls == []

    def test_threshold_is_applied_once_for_the_whole_batch(
        self, client, seed_lock_configuration, mongo_db
    ):
        session_id = "batch-session"
        seed_lock_configuration(
            session_id=session_id,
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster)
            session = await load_session(session_id)

            # Five scans in one window: two complete thresholds are claimed.
            for _ in range(5):
                batcher.record_nowait(
                    session,
                    [{"label": PuryfiObjectLabel.Buttocks}],
                )
            await batcher.flush_all()

        asyncio.run(scenario())

        # One Chaster call for both thresholds, not one call per scan.
        assert chaster.add_time_calls == [(session_id, 1200)]
        assert chaster.log_calls
        assert chaster.log_calls[0][1]["description"] == "1200 seconds added!"
        # 5 scans - 2 * limit(2) = 1 image kept for the next window.
        assert stored_count(mongo_db, session_id) == 1

    def test_deadline_is_not_moved_by_later_scans(
        self, client, seed_lock_configuration
    ):
        seed_lock_configuration(
            session_id="window-session",
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster, window_seconds=10.0)
            session = await load_session("window-session")

            batcher.record_nowait(
                session,
                [{"label": PuryfiObjectLabel.Buttocks}],
            )
            batch = batcher._batches["window-session"]
            first_deadline = batch.due_at

            batcher.record_nowait(
                session,
                [{"label": PuryfiObjectLabel.Anus}],
            )

            assert batch.due_at == first_deadline
            assert batch.count == 2

        asyncio.run(scenario())

    def test_scheduler_flushes_after_the_window(
        self, client, seed_lock_configuration, mongo_db
    ):
        seed_lock_configuration(
            session_id="scheduled-session",
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster, window_seconds=0.02)
            await batcher.start()
            try:
                session = await load_session("scheduled-session")
                batcher.record_nowait(
                    session,
                    [{"label": PuryfiObjectLabel.Buttocks}],
                )
                for _ in range(100):
                    if stored_count(mongo_db, "scheduled-session") == 1:
                        break
                    await asyncio.sleep(0.01)
            finally:
                await batcher.stop()

        asyncio.run(scenario())

        assert stored_count(mongo_db, "scheduled-session") == 1

    def test_failed_add_time_restores_the_counter_and_retries(
        self, client, seed_lock_configuration, mongo_db
    ):
        session_id = "retry-session"
        seed_lock_configuration(
            session_id=session_id,
            seen_censored_objects=1,
            config=enabled_config(),
        )
        chaster = FakeChaster(outcomes=[False, True])

        async def scenario():
            batcher = make_batcher(chaster)
            session = await load_session(session_id)
            batcher.record_nowait(
                session,
                [{"label": PuryfiObjectLabel.Buttocks}],
            )

            # First attempt fails: the claimed block is restored.
            await batcher.flush_all()
            assert stored_count(mongo_db, session_id) == 2
            assert chaster.add_time_calls == [(session_id, 600)]

            # The persisted counter is retried even without a new scan.
            await batcher.flush_all()

        asyncio.run(scenario())

        assert chaster.add_time_calls == [(session_id, 600), (session_id, 600)]
        assert stored_count(mongo_db, session_id) == 0

    def test_disabled_feature_does_not_buffer_or_count(
        self, client, seed_lock_configuration, mongo_db
    ):
        session_id = "disabled-session"
        seed_lock_configuration(session_id=session_id)
        chaster = FakeChaster()

        async def scenario():
            batcher = make_batcher(chaster)
            session = await load_session(session_id)
            batcher.record_nowait(
                session,
                [{"label": PuryfiObjectLabel.Buttocks}],
            )
            await batcher.flush_all()
            assert batcher.pending_sessions == 0

        asyncio.run(scenario())

        assert stored_count(mongo_db, session_id) == 0
        assert chaster.add_time_calls == []

    def test_stop_flushes_pending_batches(
        self, client, seed_lock_configuration, mongo_db
    ):
        session_id = "shutdown-session"
        seed_lock_configuration(
            session_id=session_id,
            config=enabled_config(),
        )
        chaster = FakeChaster()

        async def scenario():
            # Long window: only the shutdown flush can persist this scan.
            batcher = make_batcher(chaster, window_seconds=60.0)
            session = await load_session(session_id)
            batcher.record_nowait(
                session,
                [{"label": PuryfiObjectLabel.Buttocks}],
            )
            await batcher.stop()

        asyncio.run(scenario())

        assert stored_count(mongo_db, session_id) == 1

    def test_claim_is_atomic_and_never_claims_partial_thresholds(
        self, client, seed_lock_configuration, mongo_db
    ):
        session_id = "claim-session"
        seed_lock_configuration(session_id=session_id, seen_censored_objects=5)

        async def scenario():
            sessions = MongoLockSessionRepository()
            assert await sessions.claim_censored_penalties(session_id, 2, 2) == 4
            assert stored_count(mongo_db, session_id) == 1
            # Only one worker can claim the same block.
            assert await sessions.claim_censored_penalties(session_id, 2, 2) == 0
            assert stored_count(mongo_db, session_id) == 1

        asyncio.run(scenario())


class TestConnectionScanOffload:
    def test_scan_is_forwarded_to_the_non_blocking_sink(self):
        sink = RecordingSink()
        connection = Connection(
            FakeWebSocket(),
            FakeLockConfig(),
            media_scans=sink,
        )

        asyncio.run(
            connection.handle_message(
                scan_message([
                    PuryfiObjectLabel.FemaleBreast,
                    PuryfiObjectLabel.Buttocks,
                ])
            )
        )

        assert len(sink.calls) == 1
        assert sink.calls[0][1] == [
            {"label": PuryfiObjectLabel.FemaleBreast},
            {"label": PuryfiObjectLabel.Buttocks},
        ]

    def test_scan_is_ignored_when_no_sink_is_configured(self):
        connection = Connection(FakeWebSocket(), FakeLockConfig())

        # Must not raise or touch the network/database.
        asyncio.run(
            connection.handle_message(
                scan_message([PuryfiObjectLabel.Buttocks])
            )
        )

    def test_sink_failure_does_not_escape_the_read_loop(self):
        class ExplodingSink:
            def record_nowait(self, session, objects) -> None:
                raise RuntimeError("sink failed")

        connection = Connection(
            FakeWebSocket(),
            FakeLockConfig(),
            media_scans=ExplodingSink(),
        )

        # A bad scan must not close the PuryFi socket.
        asyncio.run(
            connection.handle_message(
                scan_message([PuryfiObjectLabel.Buttocks])
            )
        )
