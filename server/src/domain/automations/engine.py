"""In-memory automation rule engine.

The hot path (``record_nowait``) is deliberately synchronous and I/O-free: it
only updates counters in memory. Threshold crossings create a supervised task
that persists the execution and runs actions outside the WebSocket read loop.
Counters are flushed to MongoDB in batches every 15 seconds.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from domain.automation_models import (
    CONDITION_OPERATORS,
    EVENT_PURYFI_MEDIA_SCAN,
    LEGACY_CENSORABLE_LABELS,
    AutomationActionSchema,
    AutomationCreateSchema,
    AutomationLimitsSchema,
    AutomationTriggerSchema,
    label_catalog,
)
from domain.automations.actions import ActionContext, ActionExecutor, ActionResult
from domain.entities import LockSession, PuryfiObjectLabel
from domain.ports import (
    AutomationExecutionRepository,
    AutomationRepository,
    MediaCounterRepository,
)

log = structlog.get_logger(__name__)

DEFAULT_FLUSH_SECONDS = 15.0
MIN_MEDIA_COOLDOWN_SECONDS = 5


@dataclass(slots=True)
class _CounterState:
    count: int = 0
    window_started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_triggered_at: datetime | None = None


@dataclass(slots=True)
class _CompiledRule:
    id: str
    session_id: str
    owner_id: str
    owner_role: str
    name: str
    enabled: bool
    priority: int
    trigger: AutomationTriggerSchema
    actions: list[AutomationActionSchema]
    limits: AutomationLimitsSchema
    relevant_label_mask: int = 0


class AutomationEngine:
    def __init__(
        self,
        *,
        automations: AutomationRepository,
        counters: MediaCounterRepository,
        executions: AutomationExecutionRepository,
        actions: ActionExecutor,
        flush_seconds: float = DEFAULT_FLUSH_SECONDS,
    ) -> None:
        self._automations = automations
        self._counters = counters
        self._executions = executions
        self._actions = actions
        self._flush_seconds = flush_seconds

        self._cache: dict[str, list[_CompiledRule]] = {}
        self._loaded: set[str] = set()
        self._automation_sessions: set[str] = set()
        self._counter_state: dict[tuple[str, str], _CounterState] = {}
        self._dirty: set[tuple[str, str]] = set()
        self._event_last_triggered: dict[tuple[str, str], datetime] = {}
        self._daily_counts: dict[tuple[str, str], tuple[date, int]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._flush_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._sequence = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._flush_task is not None:
            return
        self._stopping = False
        self._flush_task = asyncio.create_task(
            self._run_flush_loop(), name="automation-counter-flush"
        )
        log.info("automation.engine_started", flush_seconds=self._flush_seconds)

    async def stop(self) -> None:
        self._stopping = True
        task = self._flush_task
        self._flush_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        for pending in list(self._tasks):
            pending.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self.flush_all()
        log.info("automation.engine_stopped")

    async def _run_flush_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self._flush_seconds)
            try:
                await self.flush_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("automation.counter_flush_failed")

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------
    async def load_session(self, session: LockSession) -> None:
        session_id = session.session_id
        if session_id in self._loaded:
            return

        documents = await self._automations.list_for_session(session_id)
        compiled = [self._compile(document) for document in documents]

        counters = await self._counters.load_for_session(session_id)
        now = datetime.now(UTC)
        for document in counters:
            key = (session_id, str(document["automation_id"]))
            window_started_at = self._as_utc(
                document.get("window_started_at")
            ) or now
            last_triggered_at = self._as_utc(
                document.get("last_triggered_at")
            )
            self._counter_state[key] = _CounterState(
                count=int(document.get("occurrence_count", 0) or 0),
                window_started_at=window_started_at,
                last_triggered_at=last_triggered_at,
            )

        self._cache[session_id] = compiled
        self._loaded.add(session_id)
        if session.automation_mode or compiled:
            self._automation_sessions.add(session_id)

    async def invalidate_session(self, session_id: str) -> None:
        await self._flush_session(session_id)
        self._cache.pop(session_id, None)
        self._loaded.discard(session_id)
        self._automation_sessions.discard(session_id)
        for key in [key for key in self._counter_state if key[0] == session_id]:
            self._counter_state.pop(key, None)
        for key in [key for key in self._event_last_triggered if key[0] == session_id]:
            self._event_last_triggered.pop(key, None)
        for key in [key for key in self._daily_counts if key[0] == session_id]:
            self._daily_counts.pop(key, None)

    async def reset_counter(
        self, session_id: str, automation_id: str
    ) -> None:
        key = (session_id, automation_id)
        self._counter_state.pop(key, None)
        self._dirty.discard(key)
        await self._counters.delete_for_automation(session_id, automation_id)

    async def archive_session(self, session_id: str) -> int:
        archived = await self._automations.archive_for_session(session_id)
        # Flush/drop in-memory counters before deleting the persistent rows;
        # otherwise the invalidation flush would recreate them.
        await self.invalidate_session(session_id)
        await self._counters.delete_for_session(session_id)
        return archived

    def is_loaded(self, session_id: str) -> bool:
        return session_id in self._loaded

    def has_rules(self, session_id: str) -> bool:
        return bool(self._cache.get(session_id))

    # ------------------------------------------------------------------
    # Hot path: media scans
    # ------------------------------------------------------------------
    def record_nowait(
        self,
        session: LockSession,
        objects: Sequence[Any],
    ) -> bool:
        """Buffer one scan. Returns True when automation mode owns the scan.

        The return value lets the caller skip the legacy media batcher. Even if
        no rule matches, automation mode must stay authoritative once enabled.
        """
        if (
            not session.automation_mode
            and session.session_id not in self._automation_sessions
        ):
            return False

        try:
            rules = self._cache.get(session.session_id, [])
            if not rules:
                return True

            payload = self._scan_payload(objects)
            scan_mask = int(payload.get("label_mask", 0))
            for rule in rules:
                if not rule.enabled:
                    continue
                if rule.trigger.event != EVENT_PURYFI_MEDIA_SCAN:
                    continue
                if (
                    rule.relevant_label_mask
                    and not (scan_mask & rule.relevant_label_mask)
                ):
                    continue
                if not self._matches(rule.trigger, payload, {}):
                    continue
                self._count_match(session, rule, payload)
            return True
        except Exception:
            log.exception(
                "automation.scan_evaluation_failed",
                session_id=getattr(session, "session_id", None),
            )
            return True

    def record_event_nowait(
        self,
        session: LockSession,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> bool:
        """Evaluate a low-volume event without blocking its producer.

        PuryFi protocol events (ready, disconnect, permission/state/profile
        changes) arrive on the WebSocket read loop. Persisting executions and
        running Chaster/PuryFi actions are I/O, so they are moved to a
        supervised task like media triggers. Returns True when a matching rule
        was potentially scheduled.
        """
        if self._stopping:
            return False
        if (
            not session.automation_mode
            and session.session_id not in self._automation_sessions
        ):
            return False

        rules = self._cache.get(session.session_id)
        if not rules:
            return False
        if not any(
            rule.enabled and rule.trigger.event == event_type for rule in rules
        ):
            return False

        self._spawn(
            self.evaluate_event(
                session,
                event_type=event_type,
                payload=payload or {},
                context=context,
                event_id=event_id,
            ),
            name=f"automation-event:{event_type}",
        )
        return True

    def _count_match(
        self,
        session: LockSession,
        rule: _CompiledRule,
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        key = (session.session_id, rule.id)
        state = self._counter_state.get(key)
        if state is None:
            state = _CounterState(window_started_at=now)
            self._counter_state[key] = state

        window = rule.trigger.window_seconds
        if window > 0 and now - state.window_started_at > timedelta(seconds=window):
            state.count = 0
            state.window_started_at = now

        increment = 1
        if rule.trigger.count_mode == "objects":
            increment = self._matching_object_count(rule.trigger, payload)

        state.count += increment
        self._dirty.add(key)

        if state.count < rule.trigger.count:
            return

        cooldown = max(
            rule.limits.cooldown_seconds,
            MIN_MEDIA_COOLDOWN_SECONDS,
        )
        if (
            state.last_triggered_at is not None
            and now - state.last_triggered_at < timedelta(seconds=cooldown)
        ):
            return
        if not self._allow_daily(session.session_id, rule, now):
            return

        consumed = state.count
        state.count = 0
        state.window_started_at = now
        state.last_triggered_at = now
        self._dirty.add(key)

        self._sequence += 1
        event_id = (
            f"media:{session.session_id}:{rule.id}:"
            f"{int(now.timestamp() * 1000)}:{self._sequence}"
        )
        self._spawn(
            self._trigger(
                session,
                rule,
                event_id=event_id,
                event_type=EVENT_PURYFI_MEDIA_SCAN,
                payload=payload,
                restore_count=consumed,
            ),
            name=f"automation-trigger:{rule.id}",
        )

    @staticmethod
    def _as_utc(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return None

    @staticmethod
    def _scan_payload(objects: Sequence[Any]) -> dict[str, Any]:
        labels: set[str] = set()
        scores: list[float] = []
        label_scores: dict[str, float] = {}
        label_mask = 0

        for obj in objects:
            if not isinstance(obj, dict):
                continue
            label_value = obj.get("label")
            name: str | None = None
            if isinstance(label_value, int) and not isinstance(label_value, bool):
                name = PuryfiObjectLabel.get_name(label_value)
                if name is not None:
                    label_mask |= 1 << label_value
            elif isinstance(label_value, str):
                name = label_value if label_value in label_catalog_names() else None
                if name is not None:
                    try:
                        label_mask |= 1 << int(PuryfiObjectLabel[name])
                    except KeyError:
                        pass

            score = obj.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                score = 0.0
            score = float(score)

            if name:
                labels.add(name)
                label_scores[name] = max(label_scores.get(name, 0.0), score)
            scores.append(score)

        return {
            "objects": list(objects),
            "labels": sorted(labels),
            "label_scores": label_scores,
            "label_mask": label_mask,
            "max_score": max(scores) if scores else 0.0,
            "object_count": len(objects),
        }

    @staticmethod
    def _matching_object_count(
        trigger: AutomationTriggerSchema, payload: dict[str, Any]
    ) -> int:
        required = set()
        min_score = 0.0
        for condition in trigger.conditions:
            if condition.field == "labels":
                values = (
                    condition.value
                    if isinstance(condition.value, list)
                    else [condition.value]
                )
                required.update(str(value) for value in values)
            elif condition.field == "score" and condition.op == "gte":
                try:
                    min_score = float(condition.value)
                except (TypeError, ValueError):
                    pass

        count = 0
        for obj in payload.get("objects", []):
            if not isinstance(obj, dict):
                continue
            label_value = obj.get("label")
            name = (
                PuryfiObjectLabel.get_name(label_value)
                if isinstance(label_value, int)
                else label_value
            )
            if required and name not in required:
                continue
            score = obj.get("score")
            if (
                isinstance(score, (int, float))
                and not isinstance(score, bool)
                and float(score) < min_score
            ):
                continue
            count += 1
        return max(1, count)

    # ------------------------------------------------------------------
    # Non-media events
    # ------------------------------------------------------------------
    async def evaluate_event(
        self,
        session: LockSession,
        *,
        event_type: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.load_session(session)
        context = context or {}
        executions: list[dict[str, Any]] = []

        for rule in self._cache.get(session.session_id, []):
            if not rule.enabled:
                continue
            if rule.trigger.event != event_type:
                continue
            if not self._matches(rule.trigger, payload, context):
                continue

            key = (session.session_id, rule.id)
            now = datetime.now(UTC)
            last = self._event_last_triggered.get(key)
            if (
                last is not None
                and rule.limits.cooldown_seconds > 0
                and now - last < timedelta(seconds=rule.limits.cooldown_seconds)
            ):
                continue

            if not self._allow_daily(session.session_id, rule, now):
                continue
            self._event_last_triggered[key] = now
            execution = await self._trigger(
                session,
                rule,
                event_id=event_id or f"{event_type}:{uuid.uuid4().hex}",
                event_type=event_type,
                payload=payload,
            )
            executions.append(execution)

        return executions

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def _matches(
        self,
        trigger: AutomationTriggerSchema,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> bool:
        # A score condition applies to the labels named by the same rule when
        # possible, not to an unrelated object with a higher score.
        label_values: set[str] = set()
        for condition in trigger.conditions:
            if condition.field != "labels":
                continue
            values = (
                condition.value
                if isinstance(condition.value, list)
                else [condition.value]
            )
            label_values.update(str(value) for value in values)

        score_value = float(payload.get("max_score") or 0.0)
        if label_values:
            label_scores = payload.get("label_scores") or {}
            relevant = [
                float(label_scores[label])
                for label in label_values
                if label in label_scores
            ]
            if relevant:
                score_value = max(relevant)

        if (
            trigger.event == EVENT_PURYFI_MEDIA_SCAN
            and score_value < trigger.min_score
        ):
            return False

        for condition in trigger.conditions:
            if not self._condition_matches(
                condition, payload, context, score_value
            ):
                return False
        return True

    def _condition_matches(
        self,
        condition: Any,
        payload: dict[str, Any],
        context: dict[str, Any],
        score_value: float,
    ) -> bool:
        field = condition.field
        op = condition.op
        expected = condition.value

        if field == "labels":
            actual = set(payload.get("labels") or [])
            values = expected if isinstance(expected, list) else [expected]
            expected_set = {str(value) for value in values}
            if op == "contains_all":
                return expected_set.issubset(actual)
            if op == "contains_any":
                return bool(expected_set & actual)
            if op == "not_contains":
                return not bool(expected_set & actual)
            if op == "eq":
                return actual == expected_set
            if op == "neq":
                return actual != expected_set
            return False

        if field == "score":
            return self._compare(score_value, op, expected)
        if field == "object_count":
            return self._compare(int(payload.get("object_count") or 0), op, expected)

        if field in {
            "chaster_frozen",
            "puryfi_enabled",
            "puryfi_has_lock",
        }:
            actual = context.get(field)
            # A condition on a state the event does not know yet (for example
            # puryfi_enabled on `ready`, before the first getState) must not
            # silently behave as False.
            if actual is None:
                return False
            if op == "eq":
                return bool(actual) == bool(expected)
            if op == "neq":
                return bool(actual) != bool(expected)
            return False

        return False

    @staticmethod
    def _compare(actual: float, op: str, expected: Any) -> bool:
        try:
            value = float(expected)
        except (TypeError, ValueError):
            return False
        if op == "gte":
            return actual >= value
        if op == "lte":
            return actual <= value
        if op == "eq":
            return actual == value
        if op == "neq":
            return actual != value
        return False

    def _allow_daily(
        self, session_id: str, rule: _CompiledRule, now: datetime
    ) -> bool:
        limit = rule.limits.max_per_day
        if limit <= 0:
            return True

        key = (session_id, rule.id)
        today = now.date()
        stored_day, count = self._daily_counts.get(key, (today, 0))
        if stored_day != today:
            count = 0
        if count >= limit:
            return False
        self._daily_counts[key] = (today, count + 1)
        return True

    # ------------------------------------------------------------------
    # Trigger + persistence
    # ------------------------------------------------------------------
    async def _trigger(
        self,
        session: LockSession,
        rule: _CompiledRule,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        restore_count: int = 0,
    ) -> dict[str, Any]:
        started = datetime.now(UTC)
        execution = await self._executions.create(
            {
                "session_id": session.session_id,
                "automation_id": rule.id,
                "automation_name": rule.name,
                "event_id": event_id,
                "event_type": event_type,
                "status": "running",
                "started_at": started,
            }
        )

        results: list[ActionResult] = []
        status = "success"
        error: str | None = None
        try:
            results = await self._actions.execute(
                rule.actions,
                ActionContext(
                    session=session,
                    event_id=event_id,
                    event_type=event_type,
                ),
            )
            if any(result.status == "failed" for result in results):
                status = "partial" if any(
                    result.status == "success" for result in results
                ) else "failed"
                error = next(
                    (result.error for result in results if result.error), None
                )
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            log.exception(
                "automation.trigger_failed",
                session_id=session.session_id,
                automation_id=rule.id,
                event_id=event_id,
            )

        # A failed Chaster time penalty must not be lost. Restore the consumed
        # matches so the next scan window can retry, matching the legacy
        # media-scan service behaviour.
        time_action_failed = any(
            result.type in {"chaster.add_time", "chaster.remove_time"}
            and result.status == "failed"
            for result in results
        )
        if time_action_failed and restore_count > 0:
            key = (session.session_id, rule.id)
            state = self._counter_state.get(key)
            if state is not None:
                state.count += restore_count
                self._dirty.add(key)

        finished = datetime.now(UTC)
        action_payload = [result.as_dict() for result in results]
        await self._executions.update(
            str(execution.id),
            status=status,
            actions=action_payload,
            error=error,
            finished_at=finished,
        )
        await self._persist_counter((session.session_id, rule.id))

        return {
            "id": str(execution.id),
            "session_id": session.session_id,
            "automation_id": rule.id,
            "automation_name": rule.name,
            "event_id": event_id,
            "event_type": event_type,
            "status": status,
            "actions": action_payload,
            "error": error,
            "started_at": started,
            "finished_at": finished,
        }

    async def flush_all(self) -> None:
        keys = list(self._dirty)
        if not keys:
            return
        documents = [self._counter_document(key) for key in keys]
        await self._counters.bulk_upsert(documents)
        self._dirty.difference_update(keys)

    async def _flush_session(self, session_id: str) -> None:
        keys = [key for key in self._dirty if key[0] == session_id]
        if not keys:
            return
        await self._counters.bulk_upsert(
            [self._counter_document(key) for key in keys]
        )
        self._dirty.difference_update(keys)

    async def _persist_counter(self, key: tuple[str, str]) -> None:
        if key not in self._counter_state:
            return
        await self._counters.bulk_upsert([self._counter_document(key)])
        self._dirty.discard(key)

    def _counter_document(self, key: tuple[str, str]) -> dict[str, Any]:
        state = self._counter_state[key]
        return {
            "session_id": key[0],
            "automation_id": key[1],
            "occurrence_count": state.count,
            "window_started_at": state.window_started_at,
            "last_triggered_at": state.last_triggered_at,
            "updated_at": datetime.now(UTC),
        }

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------
    def _compile(self, document: Any) -> _CompiledRule:
        trigger = AutomationTriggerSchema.model_validate(document.trigger)
        actions = [
            AutomationActionSchema.model_validate(action)
            for action in document.actions
        ]
        limits = AutomationLimitsSchema.model_validate(document.limits or {})
        return _CompiledRule(
            id=str(document.id),
            session_id=document.session_id,
            owner_id=document.owner_id,
            owner_role=document.owner_role,
            name=document.name,
            enabled=bool(document.enabled),
            priority=document.priority,
            trigger=trigger,
            actions=actions,
            limits=limits,
            relevant_label_mask=self._label_mask(trigger),
        )

    def _compile_schema(
        self, schema: AutomationCreateSchema, *, session_id: str
    ) -> _CompiledRule:
        return _CompiledRule(
            id="preview",
            session_id=session_id,
            owner_id="preview",
            owner_role="preview",
            name=schema.name,
            enabled=schema.enabled,
            priority=schema.priority,
            trigger=schema.trigger,
            actions=schema.actions,
            limits=schema.limits,
            relevant_label_mask=self._label_mask(schema.trigger),
        )

    @staticmethod
    def _label_mask(trigger: AutomationTriggerSchema) -> int:
        mask = 0
        for condition in trigger.conditions:
            if condition.field != "labels":
                continue
            # Negative conditions must not filter the candidate set, otherwise
            # a rule such as "does not contain Eyes" would be skipped on every
            # image that does not contain Eyes.
            if condition.op not in {"contains_all", "contains_any", "eq"}:
                continue
            values = (
                condition.value
                if isinstance(condition.value, list)
                else [condition.value]
            )
            for value in values:
                try:
                    label = PuryfiObjectLabel[str(value)]
                except KeyError:
                    continue
                mask |= 1 << int(label)
        return mask

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def _spawn(self, coro, *, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            log.error(
                "automation.task_failed",
                task=task.get_name(),
                error=type(error).__name__,
                exc_info=error,
            )


# The engine's condition evaluator is intentionally small; keep this helper
# outside the class so the hot path does not rebuild the label catalog.
_LABEL_NAMES: set[str] | None = None


def label_catalog_names() -> set[str]:
    global _LABEL_NAMES
    if _LABEL_NAMES is None:
        _LABEL_NAMES = {label.value for label in label_catalog()}
    return _LABEL_NAMES


__all__ = [
    "CONDITION_OPERATORS",
    "DEFAULT_FLUSH_SECONDS",
    "LEGACY_CENSORABLE_LABELS",
    "MIN_MEDIA_COOLDOWN_SECONDS",
    "AutomationEngine",
]
