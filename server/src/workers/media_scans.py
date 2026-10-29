"""Coalesce high-volume ``staticMediaScan`` events into per-session batches.

PuryFi can emit dozens of scans per second for a single browsing user. Doing a
database write (and sometimes a Chaster call) per scan would saturate the
shared Chaster API and block the WebSocket read loop. This worker keeps a
single pending batch per session instead:

* the first censorable scan opens a fixed window (15 s by default);
* every scan in the window increments the batch counter;
* at the deadline the counter is persisted with one atomic increment, and all
  reached thresholds are applied with one ``add_time`` call.

Counters live in memory for at most one window. The durable
``seen_censored_objects`` field remains the source of truth across reconnects.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from domain.entities import LockSession
from domain.errors import SessionNotFoundError
from domain.use_cases.media_scan import MediaScanService
from infra.logging import get_logger

log = get_logger(__name__)

DEFAULT_WINDOW_SECONDS = 15.0
DEFAULT_POLL_SECONDS = 0.5
DEFAULT_RETRY_SECONDS = 15.0
DEFAULT_MAX_CONCURRENT_FLUSHES = 16
DEFAULT_MAX_CONCURRENT_PENALTIES = 4


@dataclass(slots=True)
class _PendingBatch:
    session: LockSession
    count: int = 0
    # ``None`` means "not scheduled"; e.g. while a flush is in flight.
    due_at: float | None = None
    flushing: bool = False


class MediaScanBatcher:
    """One process-wide, coalescing sink for ``staticMediaScan`` events.

    The application is single-process by design (the realtime registry is
    in-memory), so a process-wide worker is also the natural aggregation
    boundary. It survives WebSocket disconnects: a batch is flushed at its
    deadline even if the user closed the tab.
    """

    def __init__(
        self,
        *,
        scans: MediaScanService,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
        max_concurrent_flushes: int = DEFAULT_MAX_CONCURRENT_FLUSHES,
        max_concurrent_penalties: int = DEFAULT_MAX_CONCURRENT_PENALTIES,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if retry_seconds <= 0:
            raise ValueError("retry_seconds must be positive")

        self._scans = scans
        self._window_seconds = window_seconds
        self._poll_seconds = poll_seconds
        self._retry_seconds = retry_seconds

        self._batches: dict[str, _PendingBatch] = {}
        self._flush_tasks: set[asyncio.Task[None]] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

        self._flush_semaphore = asyncio.Semaphore(max_concurrent_flushes)
        self._penalty_semaphore = asyncio.Semaphore(max_concurrent_penalties)

    @property
    def pending_sessions(self) -> int:
        return len(self._batches)

    @property
    def pending_scans(self) -> int:
        return sum(batch.count for batch in self._batches.values())

    def record_nowait(
        self,
        session: LockSession,
        objects: Sequence[Any],
    ) -> None:
        """Buffer one scanned image without doing any I/O.

        Called from the WebSocket read loop. It must stay synchronous so a
        burst of scans never delays RPC responses on the same connection.
        """
        if self._stopping:
            return
        if not MediaScanService.is_censorable(objects):
            return

        config = getattr(getattr(session, "config", None), "censorPicsConfig", None)
        if not getattr(config, "enabled", False):
            return

        session_id = getattr(session, "session_id", None)
        if not isinstance(session_id, str) or not session_id:
            return

        now = asyncio.get_running_loop().time()
        batch = self._batches.get(session_id)
        if batch is None:
            batch = _PendingBatch(
                session=session,
                due_at=now + self._window_seconds,
            )
            self._batches[session_id] = batch
        else:
            # The latest connection/config wins if the user reconnected.
            batch.session = session

        batch.count += 1
        # A scan arriving while a flush is in flight belongs to the next
        # window; the flush completion schedules it. Never move an existing
        # deadline: a continuously browsing user must still flush every window.
        if not batch.flushing and batch.due_at is None:
            batch.due_at = now + self._window_seconds

    async def start(self) -> None:
        """Start the periodic scheduler (idempotent)."""
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(
            self._run(),
            name="media-scan-batcher",
        )
        log.info(
            "media_scan.worker_started",
            window_seconds=self._window_seconds,
            retry_seconds=self._retry_seconds,
        )

    async def stop(self) -> None:
        """Flush every pending batch and stop the scheduler."""
        self._stopping = True

        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        # Best effort: the process is shutting down, so a slow Chaster call
        # must not keep the application alive indefinitely.
        try:
            await asyncio.wait_for(self.flush_all(), timeout=10.0)
        except TimeoutError:
            log.warning("media_scan.shutdown_flush_timeout")
        except Exception:
            log.exception("media_scan.shutdown_flush_failed")

        # A scan may have arrived while the initial flush was in flight. Give
        # those counts one final chance before the process exits.
        try:
            await self._flush_remaining_counts()
        except Exception:
            log.exception("media_scan.shutdown_flush_failed")

        for flush_task in list(self._flush_tasks):
            flush_task.cancel()
        if self._flush_tasks:
            await asyncio.gather(*self._flush_tasks, return_exceptions=True)

        log.info("media_scan.worker_stopped", pending_sessions=len(self._batches))

    async def flush_due(self) -> None:
        """Flush batches whose deadline has passed and wait for them.

        Exposed for tests and deterministic shutdown paths. The periodic
        scheduler uses the non-awaiting ``_spawn_due`` variant.
        """
        self._spawn_due(asyncio.get_running_loop().time())
        if self._flush_tasks:
            await asyncio.gather(*list(self._flush_tasks), return_exceptions=True)

    async def flush_all(self) -> None:
        """Flush every pending batch immediately, regardless of its deadline."""
        for batch in list(self._batches.values()):
            if not batch.flushing:
                self._start_flush(batch)
        if self._flush_tasks:
            await asyncio.gather(*list(self._flush_tasks), return_exceptions=True)

    async def _flush_remaining_counts(self) -> None:
        """Flush counts that arrived while a previous flush was in flight."""
        for batch in list(self._batches.values()):
            if not batch.flushing and batch.count > 0:
                self._start_flush(batch)
        if self._flush_tasks:
            await asyncio.gather(*list(self._flush_tasks), return_exceptions=True)

    async def _run(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self._poll_seconds)
            try:
                self._spawn_due(asyncio.get_running_loop().time())
            except Exception:
                log.exception("media_scan.scheduler_error")

    def _spawn_due(self, now: float) -> None:
        for batch in list(self._batches.values()):
            if (
                batch.flushing
                or batch.due_at is None
                or batch.due_at > now
            ):
                continue
            self._start_flush(batch)

    def _start_flush(self, batch: _PendingBatch) -> None:
        batch.flushing = True
        batch.due_at = None
        task = asyncio.create_task(
            self._flush(batch),
            name=f"media-scan-flush:{batch.session.session_id}",
        )
        self._flush_tasks.add(task)
        task.add_done_callback(self._flush_done)

    def _flush_done(self, task: asyncio.Task[None]) -> None:
        self._flush_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error(
                "media_scan.flush_task_failed",
                error=type(exc).__name__,
                exc_info=exc,
            )

    async def _flush(self, batch: _PendingBatch) -> None:
        session_id = batch.session.session_id
        snapshot = batch.count
        batch.count = 0
        retry = False
        try:
            try:
                async with self._flush_semaphore:
                    penalty = await self._scans.record_batch(
                        batch.session,
                        snapshot,
                    )
            except SessionNotFoundError:
                # The Chaster session was deleted while scans were pending.
                log.info("media_scan.session_gone", session_id=session_id)
                batch.count = 0
                return
            except asyncio.CancelledError:
                batch.count += snapshot
                raise
            except Exception:
                log.exception(
                    "media_scan.flush_failed",
                    session_id=session_id,
                    count=snapshot,
                )
                batch.count += snapshot
                retry = True
                return

            if penalty is not None:
                try:
                    async with self._penalty_semaphore:
                        applied = await self._scans.apply_penalty(penalty)
                except asyncio.CancelledError:
                    # The penalty service restores the counter on failure;
                    # this path only matters during shutdown.
                    raise
                except Exception:
                    log.exception(
                        "media_scan.penalty_failed",
                        session_id=session_id,
                        duration=penalty.duration,
                    )
                    applied = False
                if not applied:
                    retry = True
        finally:
            batch.flushing = False
            now = asyncio.get_running_loop().time()
            if retry:
                # The count is durable (or restored) in MongoDB; retry even
                # when no new scan arrives, so a failed Chaster call is not
                # stuck forever.
                batch.due_at = now + self._retry_seconds
                self._batches[session_id] = batch
            elif batch.count > 0:
                batch.due_at = now + self._window_seconds
                self._batches[session_id] = batch
            elif batch.due_at is None:
                self._batches.pop(session_id, None)
