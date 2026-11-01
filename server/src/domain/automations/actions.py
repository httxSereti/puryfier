"""Execute declarative automation actions against PuryFi and Chaster."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from domain.automation_models import AutomationActionSchema
from domain.entities import LockSession
from domain.ports import (
    ChasterGateway,
    LockSessionRepository,
    MessageQueue,
    PuryfiRegistry,
)

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class ActionContext:
    session: LockSession
    event_id: str
    event_type: str


@dataclass(slots=True)
class ActionResult:
    type: str
    status: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type, "status": self.status}
        if self.error:
            result["error"] = self.error
        return result


class ActionExecutor:
    """Run one automation's actions in order.

    PuryFi commands always go through the durable queue. Chaster calls are
    made directly, but adjacent ``chaster.add_time`` actions are coalesced into
    one API call so a burst of matching rules cannot spam the Chaster API.
    """

    def __init__(
        self,
        *,
        sessions: LockSessionRepository,
        chaster: ChasterGateway,
        puryfi: PuryfiRegistry,
        queue: MessageQueue,
    ) -> None:
        self._sessions = sessions
        self._chaster = chaster
        self._puryfi = puryfi
        self._queue = queue
        # Chaster add_time calls are serialized per session with a small gap so
        # several rules triggering on the same scan cannot burst the API.
        self._add_time_locks: dict[str, asyncio.Lock] = {}
        self._last_add_time: dict[str, float] = {}

    async def execute(
        self,
        actions: list[AutomationActionSchema],
        context: ActionContext,
    ) -> list[ActionResult]:
        results: list[ActionResult] = []
        index = 0

        while index < len(actions):
            action = actions[index]

            if action.type in {"chaster.add_time", "chaster.remove_time"}:
                action_type = action.type
                total_seconds = 0
                group: list[AutomationActionSchema] = []
                while (
                    index < len(actions)
                    and actions[index].type == action_type
                ):
                    current = actions[index]
                    seconds = self._int_param(current, "seconds")
                    if seconds is None or seconds <= 0:
                        group.append(current)
                    else:
                        total_seconds += seconds
                        group.append(current)
                    index += 1

                success = False
                error: str | None = None
                if total_seconds > 0:
                    success = await self._change_time(
                        context.session.session_id,
                        total_seconds,
                        remove=action_type == "chaster.remove_time",
                    )
                    if not success:
                        error = "Chaster rejected the time action"
                else:
                    error = "seconds must be a positive integer"

                for _ in group:
                    results.append(
                        ActionResult(
                            type=action_type,
                            status="success" if success else "failed",
                            error=error,
                        )
                    )
                    if not success and action.on_failure == "stop":
                        return results
                continue

            result = await self._execute_one(action, context)
            results.append(result)
            index += 1

            if result.status == "failed" and action.on_failure == "stop":
                break

        return results

    async def _execute_one(
        self, action: AutomationActionSchema, context: ActionContext
    ) -> ActionResult:
        try:
            if action.type == "chaster.log":
                title = str(action.params.get("title") or "Puryfier automation")
                description = str(action.params.get("description") or "")
                success = await self._chaster.create_log(
                    context.session.session_id,
                    role="extension",
                    title=title,
                    description=description,
                    icon=str(action.params.get("icon") or "link"),
                    color=str(action.params.get("color") or "#ffffff"),
                )
                return ActionResult(
                    type=action.type,
                    status="success" if success else "failed",
                    error=None if success else "Chaster rejected the log",
                )

            if action.type.startswith("puryfi."):
                return await self._execute_puryfi(action, context)

            return ActionResult(
                type=action.type,
                status="failed",
                error=f"Unsupported action: {action.type}",
            )
        except Exception as exc:
            log.exception(
                "automation.action_failed",
                session_id=context.session.session_id,
                action_type=action.type,
                event_id=context.event_id,
            )
            return ActionResult(
                type=action.type,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _execute_puryfi(
        self, action: AutomationActionSchema, context: ActionContext
    ) -> ActionResult:
        session = context.session
        link_token = session.link_token
        if not link_token:
            return ActionResult(
                type=action.type,
                status="failed",
                error="This lock has no PuryFi link token",
            )

        commands: list[tuple[str, dict[str, Any]]] = []

        if action.type == "puryfi.enable":
            commands.append(("setState", {"path": "enabled", "value": True}))
        elif action.type == "puryfi.disable":
            commands.append(("setState", {"path": "enabled", "value": False}))
        elif action.type in {"puryfi.lock", "puryfi.set_lock"}:
            requested_password = action.params.get("password")
            if action.type == "puryfi.set_lock":
                if (
                    not isinstance(requested_password, str)
                    or not requested_password
                ):
                    return ActionResult(
                        type=action.type,
                        status="failed",
                        error="password is required for puryfi.set_lock",
                    )
                password = requested_password
            else:
                # Reapplying a lock must not silently rotate the emergency
                # password: reuse the stored one and only generate a password
                # when this lock never had one.
                password = session.lock_password
                if not password:
                    password = (
                        requested_password
                        if isinstance(requested_password, str)
                        and requested_password
                        else secrets.token_urlsafe(16)
                    )

            if password != session.lock_password:
                await self._sessions.update(
                    session.session_id, lock_password=password
                )
                session.lock_password = password

            timer_seconds = self._int_param(action, "timer_seconds")
            timer = None
            if timer_seconds and timer_seconds > 0:
                end_time = int(
                    (datetime.now(UTC).timestamp() + timer_seconds) * 1000
                )
                timer = {"endTime": end_time}

            timer_plus = action.params.get("timer_plus")
            if timer_plus is not None and not isinstance(timer_plus, dict):
                return ActionResult(
                    type=action.type,
                    status="failed",
                    error="timer_plus must be an object",
                )

            commands.append(
                (
                    "setState",
                    {
                        "path": "lockConfiguration",
                        "value": {
                            "password": {"secret": password},
                            "timer": timer,
                            "timerPlus": timer_plus,
                        },
                    },
                )
            )
        elif action.type == "puryfi.unlock":
            password = session.lock_password
            if not password:
                return ActionResult(
                    type=action.type,
                    status="failed",
                    error="No stored PuryFi password for this lock",
                )
            commands.append(("enterLockPassword", {"secret": password}))
        elif action.type == "puryfi.enter_emergency_token":
            token = action.params.get("token")
            if not isinstance(token, str) or not token:
                return ActionResult(
                    type=action.type,
                    status="failed",
                    error="token is required",
                )
            commands.append(
                ("enterLockEmergencyServerToken", {"emergencyServerToken": token})
            )
        else:
            return ActionResult(
                type=action.type,
                status="failed",
                error=f"Unsupported PuryFi action: {action.type}",
            )

        for msg_type, payload in commands:
            await self._queue.enqueue(link_token, msg_type, payload)

        connection = self._puryfi.get(link_token)
        delivered = False
        if connection is not None and connection.ready and connection.intents_granted:
            try:
                delivered = await connection.flush_queue()
            except Exception:
                log.warning(
                    "automation.flush_failed",
                    session_id=session.session_id,
                    action_type=action.type,
                    exc_info=True,
                )

        return ActionResult(
            type=action.type,
            status="success" if delivered else "queued",
        )

    async def _change_time(
        self, session_id: str, seconds: int, *, remove: bool
    ) -> bool:
        lock = self._add_time_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            loop = asyncio.get_running_loop()
            wait = self._last_add_time.get(session_id, 0.0) + 1.0 - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                if remove:
                    return await self._chaster.remove_time(session_id, seconds)
                return await self._chaster.add_time(session_id, seconds)
            except Exception:
                log.exception(
                    "automation.time_action_failed",
                    session_id=session_id,
                    duration=seconds,
                    remove=remove,
                )
                return False
            finally:
                self._last_add_time[session_id] = loop.time()

    @staticmethod
    def _int_param(action: AutomationActionSchema, name: str) -> int | None:
        value = action.params.get(name)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None
