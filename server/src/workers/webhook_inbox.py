import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import structlog
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from infra.documents.webhook_inbox_entry import WebhookInboxEntry
from infra.logging import get_logger
from infra.redaction import redact_path

log = get_logger(__name__)


class WebhookInboxWorker:
    """Durable, single-process worker for Chaster webhooks.

    The HTTP endpoint only validates and stores an event, so Chaster gets a
    response in milliseconds. This worker leases pending entries, dispatches
    them to the handlers, and retries transient failures with backoff.
    """

    poll_interval = 0.5
    lease_seconds = 300
    max_attempts = 5
    retry_base_seconds = 5
    retry_max_seconds = 300

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None:
            return

        self._stopping = False
        # A fresh Event per event loop: TestClient and uvicorn each start a
        # worker in their own loop.
        self._wake = asyncio.Event()
        await self._recover_processing()
        self._task = asyncio.create_task(self._run(), name="webhook-inbox-worker")
        log.info("webhook.worker_started")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()

        if self._task is None:
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        log.info("webhook.worker_stopped")

    def wake(self) -> None:
        """Wake the worker after a new entry was inserted."""
        self._wake.set()

    async def enqueue(self, payload: dict, event_key: str) -> bool:
        """Store a webhook durably. Returns False when it was already seen."""
        try:
            await WebhookInboxEntry(
                event_key=event_key,
                event=payload["event"],
                request_id=payload.get("requestId"),
                payload=payload,
            ).insert()
        except DuplicateKeyError:
            return False

        self.wake()
        return True

    async def process_next(self) -> bool:
        """Claim and process one entry. Returns True when an entry was handled."""
        entry = await self._claim_next()
        if entry is None:
            return False

        try:
            with structlog.contextvars.bound_contextvars(
                webhook_event=entry.event,
                webhook_event_key=entry.event_key,
            ):
                await self._dispatch(entry)
        except asyncio.CancelledError:
            await self._release(entry)
            raise
        except Exception as exc:  # noqa: BLE001 - any handler failure must be retried
            await self._mark_failed(entry, exc)
        else:
            await self._mark_done(entry)
            log.info(
                "webhook.processed",
                event_key=entry.event_key,
                webhook_event=entry.event,
            )

        return True

    async def _run(self) -> None:
        while not self._stopping:
            self._wake.clear()
            try:
                processed = await self.process_next()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("webhook.worker_error")
                processed = False

            if processed:
                continue

            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    async def _recover_processing(self) -> None:
        """Requeue entries left in `processing` by a previous process.

        Safe because the application is explicitly single-worker; once Redis
        or another shared lease store is added, this must be removed.
        """
        now = datetime.now(UTC)
        result = await WebhookInboxEntry.get_pymongo_collection().update_many(
            {"status": "processing"},
            {
                "$set": {
                    "status": "pending",
                    "available_at": now,
                    "locked_until": None,
                    "updated_at": now,
                }
            },
        )
        if result.modified_count:
            log.warning(
                "webhook.requeued",
                count=result.modified_count,
            )

    async def _claim_next(self) -> WebhookInboxEntry | None:
        now = datetime.now(UTC)
        document = await WebhookInboxEntry.get_pymongo_collection().find_one_and_update(
            {
                "$or": [
                    {"status": "pending", "available_at": {"$lte": now}},
                    # Entries created before `available_at` existed.
                    {"status": "pending", "available_at": {"$exists": False}},
                    # Lease expired: the previous worker likely crashed.
                    {"status": "processing", "locked_until": {"$lte": now}},
                ]
            },
            {
                "$set": {
                    "status": "processing",
                    "locked_until": now + timedelta(seconds=self.lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
            },
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return WebhookInboxEntry.model_validate(document)

    async def _dispatch(self, entry: WebhookInboxEntry) -> None:
        # Imported lazily to keep the worker import light and let tests replace
        # a handler at runtime.
        from workers.handlers import (
            handle_extension_session_deleted,
            handle_extension_updated,
            handle_lock_frozen,
            handle_lock_unfrozen,
        )

        if entry.event == "extension_session.deleted":
            result = await handle_extension_session_deleted(entry.payload)
            if isinstance(result, dict) and result.get("status") == "error":
                raise RuntimeError(
                    f"handler error: {result.get('error', 'unknown')}"
                )
            return

        if entry.event != "action_log.created":
            return

        event_data = entry.payload.get("data")
        action_log = (
            event_data.get("actionLog") if isinstance(event_data, dict) else None
        )
        action_type = (
            action_log.get("type") if isinstance(action_log, dict) else None
        )
        if not isinstance(action_type, str):
            return

        handlers = {
            "lock_frozen": handle_lock_frozen,
            "lock_unfrozen": handle_lock_unfrozen,
            "extension_updated": handle_extension_updated,
        }
        handler = handlers.get(action_type)
        if handler is None:
            return

        result = await handler(entry.payload)
        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError(f"handler error: {result.get('error', 'unknown')}")

    async def _mark_done(self, entry: WebhookInboxEntry) -> None:
        now = datetime.now(UTC)
        await WebhookInboxEntry.get_pymongo_collection().update_one(
            {"_id": entry.id},
            {
                "$set": {
                    "status": "done",
                    "processed_at": now,
                    "locked_until": None,
                    "last_error": None,
                    "updated_at": now,
                }
            },
        )

    async def _release(self, entry: WebhookInboxEntry) -> None:
        """Make an entry claimable again after a graceful cancellation."""
        now = datetime.now(UTC)
        await WebhookInboxEntry.get_pymongo_collection().update_one(
            {"_id": entry.id},
            {
                "$set": {
                    "status": "pending",
                    "available_at": now,
                    "locked_until": None,
                    "updated_at": now,
                }
            },
        )

    async def _mark_failed(
        self, entry: WebhookInboxEntry, exc: Exception
    ) -> None:
        now = datetime.now(UTC)
        error = redact_path(f"{type(exc).__name__}: {exc}")[:2000]

        if entry.attempts >= self.max_attempts:
            log.error(
                "webhook.failed_permanently",
                event_key=entry.event_key,
                webhook_event=entry.event,
                attempts=entry.attempts,
                error=error,
            )
            fields = {
                "status": "failed",
                "last_error": error,
                "processed_at": now,
                "locked_until": None,
                "updated_at": now,
            }
        else:
            delay = min(
                self.retry_base_seconds * (2 ** max(0, entry.attempts - 1)),
                self.retry_max_seconds,
            )
            log.warning(
                "webhook.retry_scheduled",
                event_key=entry.event_key,
                webhook_event=entry.event,
                attempt=entry.attempts,
                max_attempts=self.max_attempts,
                retry_in=delay,
                error=error,
            )
            fields = {
                "status": "pending",
                "last_error": error,
                "available_at": now + timedelta(seconds=delay),
                "locked_until": None,
                "updated_at": now,
            }

        await WebhookInboxEntry.get_pymongo_collection().update_one(
            {"_id": entry.id}, {"$set": fields}
        )


webhook_worker = WebhookInboxWorker()
