"""Automation use cases: ownership, CRUD, duplication and migration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from domain.automation_models import (
    EVENT_CHASTER_LOCK_FROZEN,
    EVENT_CHASTER_LOCK_UNFROZEN,
    EVENT_PURYFI_MEDIA_SCAN,
    LEGACY_CENSORABLE_LABELS,
    AutomationActionSchema,
    AutomationCreateSchema,
    AutomationExecutionSchema,
    AutomationLimitsSchema,
    AutomationListSchema,
    AutomationSchema,
    AutomationTargetSchema,
    AutomationTestResultSchema,
    AutomationTriggerSchema,
    AutomationUpdateSchema,
)
from domain.automations.engine import AutomationEngine
from domain.entities import LockSession
from domain.errors import PermissionDeniedError, SessionNotFoundError
from domain.ports import (
    AutomationExecutionRepository,
    AutomationRepository,
    ChasterGateway,
    LockSessionRepository,
    PuryfiRegistry,
)

log = structlog.get_logger(__name__)

MAX_RULES_PER_SESSION = 50


@dataclass(frozen=True, slots=True)
class AutomationActor:
    owner_id: str
    role: str
    can_manage: bool


def effective_wearer_can_manage(session: LockSession) -> bool:
    if not session.keyholder_id:
        return True
    return bool(session.config.automation_permissions.wearer_can_manage)


def resolve_actor(session: LockSession, role: str) -> AutomationActor:
    if role == "keyholder":
        owner_id = session.keyholder_id
        can_manage = True
    elif role == "wearer":
        owner_id = session.wearer_id
        can_manage = effective_wearer_can_manage(session)
    else:
        raise PermissionDeniedError("Unknown Chaster role")

    if not owner_id:
        raise PermissionDeniedError(
            "Cannot resolve the creator identity for this session"
        )
    return AutomationActor(owner_id=owner_id, role=role, can_manage=can_manage)


def _lock_label(session: LockSession) -> str:
    if session.lock_id:
        return f"Lock {session.lock_id}"
    return f"Session {session.session_id}"


def _is_owner(actor: AutomationActor, rule: Any) -> bool:
    return rule.owner_id == actor.owner_id


def _rule_schema(rule: Any, actor: AutomationActor) -> AutomationSchema:
    is_owner = _is_owner(actor, rule)
    can_edit = is_owner and actor.can_manage
    can_delete = is_owner and actor.can_manage
    disabled_by_other = (
        rule.disabled_by is not None and rule.disabled_by != actor.owner_id
    )
    can_disable = actor.role == "keyholder" or (
        can_edit and not disabled_by_other
    )

    return AutomationSchema(
        id=str(rule.id),
        session_id=rule.session_id,
        lock_id=rule.lock_id,
        lock_label=rule.lock_label,
        owner_id=rule.owner_id,
        owner_role=rule.owner_role,
        name=rule.name,
        status=rule.status,
        enabled=rule.enabled,
        priority=rule.priority,
        trigger=AutomationTriggerSchema.model_validate(rule.trigger),
        actions=[
            AutomationActionSchema.model_validate(action)
            for action in rule.actions
        ],
        limits=AutomationLimitsSchema.model_validate(rule.limits or {}),
        source_automation_id=rule.source_automation_id,
        disabled_by=rule.disabled_by,
        disabled_by_role=rule.disabled_by_role,
        disabled_at=rule.disabled_at,
        archived_at=rule.archived_at,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        is_owner=is_owner,
        can_edit=can_edit,
        can_delete=can_delete,
        can_disable=can_disable,
    )


def _execution_schema(execution: Any) -> AutomationExecutionSchema:
    return AutomationExecutionSchema(
        id=str(execution.id),
        session_id=execution.session_id,
        automation_id=execution.automation_id,
        automation_name=execution.automation_name,
        event_id=execution.event_id,
        event_type=execution.event_type,
        status=execution.status,
        actions=execution.actions,
        error=execution.error,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


def _snapshot(rule: Any) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "owner_role": rule.owner_role,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "trigger": rule.trigger,
        "actions": rule.actions,
        "limits": rule.limits,
    }


def _snapshot_hash(snapshot: list[dict[str, Any]]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def sync_snapshot(
    session: LockSession,
    *,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    chaster: ChasterGateway | None,
    puryfi: PuryfiRegistry,
    configuration_token: str | None = None,
) -> None:
    """Refresh the Chaster snapshot and the live connection cache.

    MongoDB is authoritative. A Chaster write failure must not fail the rule
    operation, so this function is best-effort by design.
    """
    rules = await automations.list_for_session(session.session_id)
    snapshot = [_snapshot(rule) for rule in rules]

    config = session.config.model_copy(deep=True)
    config.automations_snapshot = snapshot
    config.automations_snapshot_version += 1
    config.automations_snapshot_hash = _snapshot_hash(snapshot)

    if chaster is not None:
        try:
            if configuration_token:
                await chaster.update_configuration(configuration_token, config)
            else:
                # Session-token flows have no configuration token; patch the
                # session's own Chaster configuration instead.
                await chaster.update_session_configuration(
                    session.session_id, config
                )
        except Exception:
            log.warning(
                "automation.chaster_snapshot_failed",
                session_id=session.session_id,
                exc_info=True,
            )

    await sessions.update(session.session_id, config=config)
    session.config = config

    if session.link_token:
        await puryfi.update_cached_config(session.link_token, config)


async def list_automations(
    session: LockSession,
    *,
    role: str,
    automations: AutomationRepository,
    executions: AutomationExecutionRepository,
    sessions: LockSessionRepository,
) -> AutomationListSchema:
    actor = resolve_actor(session, role)
    active = await automations.list_for_session(session.session_id)
    archived = await automations.list_archived_for_owner(actor.owner_id)
    recent = await executions.list_for_session(session.session_id)

    return AutomationListSchema(
        session_id=session.session_id,
        role=role,
        owner_id=actor.owner_id,
        automation_mode=session.automation_mode,
        wearer_can_manage=session.config.automation_permissions.wearer_can_manage,
        effective_wearer_can_manage=effective_wearer_can_manage(session),
        automations=[_rule_schema(rule, actor) for rule in active],
        archived_automations=[_rule_schema(rule, actor) for rule in archived],
        targets=await list_targets(
            session,
            actor=actor,
            sessions=sessions,
        ),
        executions=[_execution_schema(execution) for execution in recent],
    )


async def list_targets(
    session: LockSession,
    *,
    actor: AutomationActor,
    sessions: LockSessionRepository,
) -> list[AutomationTargetSchema]:
    documents = await sessions.list_for_owner(actor.owner_id, actor.role)
    targets: list[AutomationTargetSchema] = []
    current: AutomationTargetSchema | None = None
    for target in documents:
        if actor.role == "wearer" and not effective_wearer_can_manage(target):
            continue
        item = AutomationTargetSchema(
            session_id=target.session_id,
            lock_id=target.lock_id,
            lock_label=_lock_label(target),
            role=actor.role,
        )
        if target.session_id == session.session_id:
            current = item
            continue
        targets.append(item)

    # Keep the current lock available (notably for duplicating an archived
    # rule into this lock), but list it last so the common "duplicate to
    # another lock" flow keeps another lock as the default choice.
    if current is not None:
        targets.append(current)
    return targets


async def create_automation(
    session: LockSession,
    *,
    role: str,
    payload: AutomationCreateSchema,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    chaster: ChasterGateway,
    puryfi: PuryfiRegistry,
    engine: AutomationEngine,
    configuration_token: str | None = None,
) -> AutomationSchema:
    actor = resolve_actor(session, role)
    if not actor.can_manage:
        raise PermissionDeniedError("You cannot manage automations for this lock")

    existing = await automations.list_for_session(session.session_id)
    if len(existing) >= MAX_RULES_PER_SESSION:
        raise ValueError(
            f"This lock already has the maximum of {MAX_RULES_PER_SESSION} automations"
        )

    document = await automations.create(
        {
            "session_id": session.session_id,
            "lock_id": session.lock_id,
            "lock_label": _lock_label(session),
            "owner_id": actor.owner_id,
            "owner_role": actor.role,
            "name": payload.name,
            "status": "active",
            "enabled": payload.enabled,
            "priority": payload.priority,
            "trigger": payload.trigger.model_dump(mode="json"),
            "actions": [
                action.model_dump(mode="json") for action in payload.actions
            ],
            "limits": payload.limits.model_dump(mode="json"),
        }
    )

    await sessions.update(session.session_id, automation_mode=True)
    session.automation_mode = True
    await engine.invalidate_session(session.session_id)
    await engine.load_session(session)
    await sync_snapshot(
        session,
        automations=automations,
        sessions=sessions,
        chaster=chaster,
        puryfi=puryfi,
        configuration_token=configuration_token,
    )
    return _rule_schema(document, actor)


async def update_automation(
    session: LockSession,
    *,
    role: str,
    automation_id: str,
    payload: AutomationUpdateSchema,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    chaster: ChasterGateway,
    puryfi: PuryfiRegistry,
    engine: AutomationEngine,
    configuration_token: str | None = None,
) -> AutomationSchema:
    actor = resolve_actor(session, role)
    rule = await automations.get(automation_id)
    if rule is None or rule.session_id != session.session_id:
        raise SessionNotFoundError("Automation not found")

    is_owner = _is_owner(actor, rule)
    fields: dict[str, Any] = {}

    if is_owner and actor.can_manage:
        fields = payload.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
        if "trigger" in fields:
            fields["trigger"] = payload.trigger.model_dump(mode="json")  # type: ignore[union-attr]
        if "actions" in fields:
            fields["actions"] = [
                action.model_dump(mode="json")
                for action in (payload.actions or [])
            ]
        if "limits" in fields:
            fields["limits"] = payload.limits.model_dump(mode="json")  # type: ignore[union-attr]
        if fields.get("enabled") is True:
            fields["disabled_by"] = None
            fields["disabled_by_role"] = None
            fields["disabled_at"] = None
    else:
        if actor.role != "keyholder":
            raise PermissionDeniedError("Only the creator can edit this automation")
        if payload.enabled is None:
            raise PermissionDeniedError("The keyholder can only enable or disable this automation")
        if payload.model_dump(exclude_unset=True).keys() - {"enabled"}:
            raise PermissionDeniedError(
                "The keyholder cannot modify an automation created by someone else"
            )

        fields["enabled"] = payload.enabled
        if payload.enabled:
            fields["disabled_by"] = None
            fields["disabled_by_role"] = None
            fields["disabled_at"] = None
        else:
            fields["disabled_by"] = actor.owner_id
            fields["disabled_by_role"] = actor.role
            fields["disabled_at"] = datetime.now(UTC)

    # A wearer can never re-enable a rule disabled by the keyholder.
    if (
        fields.get("enabled") is True
        and actor.role == "wearer"
        and rule.disabled_by is not None
        and rule.disabled_by != actor.owner_id
    ):
        raise PermissionDeniedError(
            "This automation was disabled by the keyholder"
        )

    updated = await automations.update(automation_id, **fields)
    if updated is None:
        raise SessionNotFoundError("Automation not found")

    if fields.get("enabled") is False:
        await engine.reset_counter(session.session_id, automation_id)

    await engine.invalidate_session(session.session_id)
    await engine.load_session(session)
    await sync_snapshot(
        session,
        automations=automations,
        sessions=sessions,
        chaster=chaster,
        puryfi=puryfi,
        configuration_token=configuration_token,
    )
    return _rule_schema(updated, actor)


async def delete_automation(
    session: LockSession,
    *,
    role: str,
    automation_id: str,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    chaster: ChasterGateway,
    puryfi: PuryfiRegistry,
    engine: AutomationEngine,
    configuration_token: str | None = None,
) -> None:
    actor = resolve_actor(session, role)
    rule = await automations.get(automation_id)
    if rule is None or rule.session_id != session.session_id:
        raise SessionNotFoundError("Automation not found")
    if not (_is_owner(actor, rule) and actor.can_manage):
        raise PermissionDeniedError("Only the creator can delete this automation")

    await automations.delete(automation_id)
    await engine.reset_counter(session.session_id, automation_id)
    await engine.invalidate_session(session.session_id)
    await engine.load_session(session)
    await sync_snapshot(
        session,
        automations=automations,
        sessions=sessions,
        chaster=chaster,
        puryfi=puryfi,
        configuration_token=configuration_token,
    )


async def duplicate_automation(
    session: LockSession,
    *,
    role: str,
    automation_id: str,
    target_session_id: str,
    name: str | None,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    puryfi: PuryfiRegistry,
    engine: AutomationEngine,
) -> AutomationSchema:
    actor = resolve_actor(session, role)
    source = await automations.get(automation_id)
    if source is None:
        raise SessionNotFoundError("Automation not found")
    # Active rules are managed from their own lock. Archived rules may be
    # duplicated from any lock where their creator is managing automations.
    if source.session_id != session.session_id and source.status != "archived":
        raise SessionNotFoundError("Automation not found")
    if not (_is_owner(actor, source) and actor.can_manage):
        raise PermissionDeniedError("Only the creator can duplicate this automation")

    target = await sessions.get_by_session_id(target_session_id)
    if target is None:
        raise SessionNotFoundError("Target lock not found")

    if actor.role == "keyholder" and target.keyholder_id != actor.owner_id:
        raise PermissionDeniedError("You are not the keyholder of the target lock")
    if actor.role == "wearer":
        if target.wearer_id != actor.owner_id:
            raise PermissionDeniedError("You are not the wearer of the target lock")
        if not effective_wearer_can_manage(target):
            raise PermissionDeniedError(
                "The wearer cannot manage automations on the target lock"
            )

    existing = await automations.list_for_session(target.session_id)
    if len(existing) >= MAX_RULES_PER_SESSION:
        raise ValueError(
            f"The target lock already has {MAX_RULES_PER_SESSION} automations"
        )

    copied = await automations.create(
        {
            "session_id": target.session_id,
            "lock_id": target.lock_id,
            "lock_label": _lock_label(target),
            "owner_id": actor.owner_id,
            "owner_role": actor.role,
            "name": name or f"{source.name} (copy)",
            "status": "active",
            "enabled": False,
            "priority": source.priority,
            "trigger": source.trigger,
            "actions": source.actions,
            "limits": source.limits,
            "source_automation_id": str(source.id),
        }
    )

    await sessions.update(target.session_id, automation_mode=True)
    target.automation_mode = True
    await engine.invalidate_session(target.session_id)
    await engine.load_session(target)

    # The target lock's Chaster configuration token is not available here.
    # Its local snapshot is refreshed now; the Chaster snapshot will be
    # synchronised the next time that lock's configuration page is opened.
    await sync_snapshot(
        target,
        automations=automations,
        sessions=sessions,
        chaster=None,
        puryfi=puryfi,
        configuration_token=None,
    )
    return _rule_schema(copied, actor)


async def migrate_legacy(
    session: LockSession,
    *,
    role: str,
    automations: AutomationRepository,
    sessions: LockSessionRepository,
    chaster: ChasterGateway,
    puryfi: PuryfiRegistry,
    engine: AutomationEngine,
    configuration_token: str | None = None,
) -> list[AutomationSchema]:
    actor = resolve_actor(session, role)
    if not actor.can_manage:
        raise PermissionDeniedError("You cannot manage automations for this lock")

    if session.automation_mode:
        active = await automations.list_for_session(session.session_id)
        return [_rule_schema(rule, actor) for rule in active]

    config = session.config
    created: list[Any] = []

    if config.lock_on_freeze:
        created.append(
            await automations.create(
                {
                    "session_id": session.session_id,
                    "lock_id": session.lock_id,
                    "lock_label": _lock_label(session),
                    "owner_id": actor.owner_id,
                    "owner_role": actor.role,
                    "name": "Lock PuryFi on freeze",
                    "trigger": {
                        "event": EVENT_CHASTER_LOCK_FROZEN,
                        "conditions": [],
                        "min_score": 0.0,
                        "count": 1,
                        "window_seconds": 0,
                        "count_mode": "images",
                    },
                    "actions": [
                        {"type": "puryfi.lock", "params": {}, "on_failure": "stop"},
                        {"type": "puryfi.enable", "params": {}, "on_failure": "stop"},
                    ],
                    "limits": {"cooldown_seconds": 0, "max_per_day": 0},
                }
            )
        )

    if config.unlock_on_unfreeze:
        created.append(
            await automations.create(
                {
                    "session_id": session.session_id,
                    "lock_id": session.lock_id,
                    "lock_label": _lock_label(session),
                    "owner_id": actor.owner_id,
                    "owner_role": actor.role,
                    "name": "Unlock PuryFi on unfreeze",
                    "trigger": {
                        "event": EVENT_CHASTER_LOCK_UNFROZEN,
                        "conditions": [],
                        "min_score": 0.0,
                        "count": 1,
                        "window_seconds": 0,
                        "count_mode": "images",
                    },
                    "actions": [
                        {"type": "puryfi.unlock", "params": {}, "on_failure": "stop"},
                        {"type": "puryfi.disable", "params": {}, "on_failure": "stop"},
                    ],
                    "limits": {"cooldown_seconds": 0, "max_per_day": 0},
                }
            )
        )

    censor = config.censorPicsConfig
    if censor.enabled:
        created.append(
            await automations.create(
                {
                    "session_id": session.session_id,
                    "lock_id": session.lock_id,
                    "lock_label": _lock_label(session),
                    "owner_id": actor.owner_id,
                    "owner_role": actor.role,
                    "name": "Add time for censored media",
                    "trigger": {
                        "event": EVENT_PURYFI_MEDIA_SCAN,
                        "conditions": [
                            {
                                "field": "labels",
                                "op": "contains_any",
                                "value": list(LEGACY_CENSORABLE_LABELS),
                            }
                        ],
                        "min_score": 0.0,
                        "count": censor.limit_count,
                        "window_seconds": 0,
                        "count_mode": "images",
                    },
                    "actions": [
                        {
                            "type": "chaster.add_time",
                            "params": {"seconds": censor.added_duration},
                            "on_failure": "stop",
                        }
                    ],
                    "limits": {"cooldown_seconds": 5, "max_per_day": 0},
                }
            )
        )

    await sessions.update(session.session_id, automation_mode=True)
    session.automation_mode = True
    await engine.invalidate_session(session.session_id)
    await engine.load_session(session)
    await sync_snapshot(
        session,
        automations=automations,
        sessions=sessions,
        chaster=chaster,
        puryfi=puryfi,
        configuration_token=configuration_token,
    )
    return [_rule_schema(rule, actor) for rule in created]


async def test_automation(
    session: LockSession,
    *,
    role: str,
    automation_id: str,
    event: dict[str, Any] | None,
    automations: AutomationRepository,
    engine: AutomationEngine,
) -> AutomationTestResultSchema:
    actor = resolve_actor(session, role)
    rule = await automations.get(automation_id)
    if rule is None:
        raise SessionNotFoundError("Automation not found")
    if rule.session_id != session.session_id and not (
        rule.status == "archived" and rule.owner_id == actor.owner_id
    ):
        raise SessionNotFoundError("Automation not found")

    schema = AutomationCreateSchema(
        name=rule.name,
        enabled=rule.enabled,
        priority=rule.priority,
        trigger=AutomationTriggerSchema.model_validate(rule.trigger),
        actions=[
            AutomationActionSchema.model_validate(action)
            for action in rule.actions
        ],
        limits=AutomationLimitsSchema.model_validate(rule.limits or {}),
    )
    result = await engine.test_rule(session, schema, event)
    return AutomationTestResultSchema(**result)
