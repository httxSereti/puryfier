"""Tests for the automation rule engine and HTTP API."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId
from conftest import WEBHOOK_AUTH
from pydantic import ValidationError
from test_extensions import make_chaster_response, make_configuration_response
from test_webhooks_chaster import wait_for_inbox

from domain.automation_models import (
    EVENT_PURYFI_MEDIA_SCAN,
    EVENT_PURYFI_STATE_CHANGED,
    AutomationActionSchema,
    automation_catalog,
)
from domain.automations.actions import (
    ActionContext,
    ActionExecutor,
    ActionResult,
)
from domain.automations.engine import AutomationEngine
from domain.entities import ChasterExtensionConfigSchema, LockSession

SESSION_ID = "automation-session"
KEYHOLDER_ID = "keyholder-1"
WEARER_ID = "wearer-1"


def automation_payload(
    *,
    name: str = "Lock on freeze",
    event: str = "chaster.lock.frozen",
    actions: list[dict] | None = None,
) -> dict:
    return {
        "name": name,
        "enabled": True,
        "priority": 100,
        "trigger": {
            "event": event,
            "conditions": [],
            "count": 1,
            "window_seconds": 0,
            "count_mode": "images",
        },
        "actions": actions
        or [
            {"type": "puryfi.lock", "params": {}, "on_failure": "stop"},
            {"type": "puryfi.enable", "params": {}, "on_failure": "stop"},
        ],
        "limits": {"cooldown_seconds": 0, "max_per_day": 0},
    }


def seed_automation_session(seed_lock_configuration, **overrides):
    config = {
        "lock_on_freeze": False,
        "unlock_on_unfreeze": False,
        "censorPicsConfig": {
            "limit_count": 100,
            "added_duration": 600,
            "enabled": False,
        },
    }
    config.update(overrides.pop("config", {}))
    return seed_lock_configuration(
        session_id=SESSION_ID,
        keyholder_id=KEYHOLDER_ID,
        wearer_id=WEARER_ID,
        config=config,
        **overrides,
    )


class TestAutomationApi:
    def test_keyholder_can_create_and_list(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )

        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["owner_id"] == KEYHOLDER_ID
        assert body["owner_role"] == "keyholder"
        assert body["enabled"] is True
        assert body["can_edit"] is True

        listed = client.get("/api/configuration/config-token/automations")
        assert listed.status_code == 200, listed.text
        payload = listed.json()
        assert len(payload["automations"]) == 1
        assert payload["automation_mode"] is True
        assert payload["effective_wearer_can_manage"] is False

    def test_remove_time_action_is_accepted(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        response = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(
                name="Reward",
                event="puryfi.media.scan",
                actions=[
                    {
                        "type": "chaster.remove_time",
                        "params": {"seconds": 60},
                        "on_failure": "stop",
                    }
                ],
            ),
        )
        assert response.status_code == 201, response.text
        assert response.json()["actions"][0]["type"] == "chaster.remove_time"

    def test_chaster_lock_actions_are_accepted(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        actions = [
            {"type": "chaster.freeze", "params": {}, "on_failure": "stop"},
            {"type": "chaster.unfreeze", "params": {}, "on_failure": "stop"},
            {"type": "chaster.toggle_freeze", "params": {}, "on_failure": "stop"},
            {
                "type": "chaster.pillory",
                "params": {"duration": 300, "reason": "Censored media"},
                "on_failure": "stop",
            },
            {
                "type": "chaster.set_timer_visibility",
                "params": {"display_remaining_time": False},
                "on_failure": "stop",
            },
        ]
        response = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(name="Lock actions", actions=actions),
        )
        assert response.status_code == 201, response.text
        assert [action["type"] for action in response.json()["actions"]] == [
            action["type"] for action in actions
        ]

    def test_wearer_is_denied_without_permission(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(role="wearer", session_id=SESSION_ID)
        )

        response = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        assert response.status_code == 403

    def test_wearer_can_manage_when_enabled(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(
            seed_lock_configuration,
            config={"automation_permissions": {"wearer_can_manage": True}},
        )
        mock_chaster_api(
            make_configuration_response(role="wearer", session_id=SESSION_ID)
        )

        response = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(name="Wearer rule"),
        )
        assert response.status_code == 201, response.text
        assert response.json()["owner_id"] == WEARER_ID

    def test_keyholder_can_disable_wearer_rule_but_wearer_cannot_reenable(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(
            seed_lock_configuration,
            config={"automation_permissions": {"wearer_can_manage": True}},
        )
        mock_chaster_api(
            make_configuration_response(role="wearer", session_id=SESSION_ID)
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(name="Wearer rule"),
        )
        automation_id = created.json()["id"]

        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        disabled = client.patch(
            f"/api/configuration/config-token/automations/{automation_id}",
            json={"enabled": False},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["disabled_by"] == KEYHOLDER_ID
        assert disabled.json()["disabled_by_role"] == "keyholder"

        mock_chaster_api(
            make_configuration_response(role="wearer", session_id=SESSION_ID)
        )
        reenabled = client.patch(
            f"/api/configuration/config-token/automations/{automation_id}",
            json={"enabled": True},
        )
        assert reenabled.status_code == 403

    def test_duplicate_creates_a_disabled_copy_in_target_lock(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(seed_lock_configuration)
        seed_lock_configuration(
            session_id="target-session",
            link_token="target-token",
            keyholder_id=KEYHOLDER_ID,
            wearer_id=WEARER_ID,
            config={},
        )
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        automation_id = created.json()["id"]

        listed = client.get("/api/configuration/config-token/automations")
        target_ids = [target["session_id"] for target in listed.json()["targets"]]
        assert "target-session" in target_ids

        duplicated = client.post(
            f"/api/configuration/config-token/automations/{automation_id}/duplicate",
            json={"target_session_id": "target-session"},
        )
        assert duplicated.status_code == 201, duplicated.text
        copy = duplicated.json()
        assert copy["session_id"] == "target-session"
        assert copy["enabled"] is False
        assert copy["source_automation_id"] == automation_id
        assert mongo_db["automations"].count_documents({}) == 2
        target = mongo_db["users_lock_configurations"].find_one(
            {"session_id": "target-session"}
        )
        assert target["automation_mode"] is True

    def test_freeze_uses_automation_engine_when_mode_is_enabled(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        assert created.status_code == 201, created.text

        from workers.handlers import handle_lock_frozen

        payload = {
            "event": "action_log.created",
            "requestId": "req-freeze-1",
            "data": {
                "sessionId": SESSION_ID,
                "actionLog": {"_id": "log-1", "type": "lock_frozen"},
            },
        }
        result = asyncio.run(handle_lock_frozen(payload))
        assert result["action"] == "automation_processed"

        queued = list(
            mongo_db["queued_messages"]
            .find({"link_token": "token-1"})
            .sort("_id", 1)
        )
        assert [message["msg_type"] for message in queued] == [
            "setState",
            "setState",
        ]
        assert queued[0]["payload"]["path"] == "lockConfiguration"
        assert queued[1]["payload"] == {"path": "enabled", "value": True}
        session = mongo_db["users_lock_configurations"].find_one(
            {"session_id": SESSION_ID}
        )
        assert session["lock_password"]

    def test_disconnect_event_runs_an_automation(
        self,
        client,
        seed_lock_configuration,
        mock_chaster_api,
        mongo_db,
    ):
        import time

        import msgpack

        from models.connection_manager import manager

        manager._connections.clear()
        manager._locks.clear()
        seed_automation_session(
            seed_lock_configuration,
            chaster_frozen=True,
        )
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(
                name="Warn on disconnect",
                event="puryfi.connection.disconnected",
                actions=[
                    {
                        "type": "chaster.log",
                        "params": {"title": "PuryFi disconnected"},
                        "on_failure": "continue",
                    }
                ],
            ),
        )
        assert created.status_code == 201, created.text

        with client.websocket_connect("/ws/token-1") as puryfi:
            puryfi.send_bytes(
                msgpack.packb(
                    {
                        "type": "ready",
                        "payload": {
                            "version": "0.8.7.1",
                            "apiVersion": "1.0.0",
                            "instanceId": "test-instance",
                        },
                        "responseId": 1,
                    }
                )
            )
            # Wait for the ready acknowledgement before closing, so the
            # connection is considered connected by the cleanup path.
            puryfi.receive_bytes()

        for _ in range(200):
            execution = mongo_db["automation_executions"].find_one(
                {"event_type": "puryfi.connection.disconnected"}
            )
            if execution is not None and execution["status"] != "running":
                break
            time.sleep(0.01)

        assert execution is not None
        assert execution["status"] == "success"
        assert [action["type"] for action in execution["actions"]] == [
            "chaster.log"
        ]

    def test_test_endpoint_returns_a_dry_run_result(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        automation_id = created.json()["id"]

        response = client.post(
            f"/api/configuration/config-token/automations/{automation_id}/test",
            json={},
        )
        assert response.status_code == 200, response.text
        assert response.json()["matched"] is True

    def test_session_endpoint_lists_rules(
        self, client, seed_lock_configuration, mock_chaster_api
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_chaster_response(role="wearer", session_id=SESSION_ID)
        )

        response = client.get("/api/session/main-token/automations")
        assert response.status_code == 200, response.text
        assert response.json()["session_id"] == SESSION_ID
        assert response.json()["role"] == "wearer"

    def test_session_joined_webhook_runs_automation(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(
                name="Lock on join",
                event="chaster.session.joined",
            ),
        )
        assert created.status_code == 201, created.text

        payload = {
            "event": "extension_session.created",
            "requestId": "req-join-1",
            "data": {
                "session": {
                    "sessionId": SESSION_ID,
                    "lock": {
                        "_id": "lock-1",
                        "keyholder": {"_id": KEYHOLDER_ID},
                        "user": {"_id": WEARER_ID},
                    },
                }
            },
        }
        response = client.post(
            "/api/webhooks/extensions/chaster",
            json=payload,
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 202
        entry = wait_for_inbox(
            mongo_db, f"extension_session.created:{SESSION_ID}"
        )
        assert entry["status"] == "done"

        queued = list(
            mongo_db["queued_messages"]
            .find({"link_token": "token-1"})
            .sort("_id", 1)
        )
        assert [message["msg_type"] for message in queued] == [
            "setState",
            "setState",
        ]

    def test_session_left_webhook_runs_automation(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(
            seed_lock_configuration,
            lock_password="s3cret",
        )
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(
                name="Unlock on leave",
                event="chaster.session.left",
                actions=[
                    {
                        "type": "puryfi.unlock",
                        "params": {},
                        "on_failure": "stop",
                    },
                    {
                        "type": "puryfi.disable",
                        "params": {},
                        "on_failure": "stop",
                    },
                ],
            ),
        )
        assert created.status_code == 201, created.text

        payload = {
            "event": "extension_session.deleted",
            "requestId": "req-leave-1",
            "data": {"session": {"sessionId": SESSION_ID}},
        }
        response = client.post(
            "/api/webhooks/extensions/chaster",
            json=payload,
            auth=WEBHOOK_AUTH,
        )
        assert response.status_code == 202
        entry = wait_for_inbox(
            mongo_db, f"extension_session.deleted:{SESSION_ID}"
        )
        assert entry["status"] == "done"

        execution = mongo_db["automation_executions"].find_one(
            {"event_type": "chaster.session.left"}
        )
        assert execution is not None
        assert execution["status"] == "success"
        assert [action["type"] for action in execution["actions"]] == [
            "puryfi.unlock",
            "puryfi.disable",
        ]

    def test_session_deletion_archives_rules(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(seed_lock_configuration)
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )
        created = client.post(
            "/api/configuration/config-token/automations",
            json=automation_payload(),
        )
        automation_id = created.json()["id"]

        from workers.handlers import handle_extension_session_deleted

        result = asyncio.run(
            handle_extension_session_deleted(
                {
                    "event": "extension_session.deleted",
                    "requestId": "req-delete-1",
                    "data": {"session": {"sessionId": SESSION_ID}},
                }
            )
        )
        assert result["action"] == "extension_session_deleted_processed"
        archived = mongo_db["automations"].find_one(
            {"_id": ObjectId(automation_id)}
        )
        assert archived["status"] == "archived"
        assert archived["enabled"] is False
        assert archived["archived_at"] is not None
        assert mongo_db["users_lock_configurations"].find_one(
            {"session_id": SESSION_ID}
        ) is None

        # The archived rule remains available for duplication from a new lock.
        seed_lock_configuration(
            session_id="new-session",
            link_token="new-token",
            keyholder_id=KEYHOLDER_ID,
            wearer_id=WEARER_ID,
            config={},
        )
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id="new-session"
            )
        )
        listed = client.get("/api/configuration/config-token/automations")
        archived_id = listed.json()["archived_automations"][0]["id"]
        duplicated = client.post(
            f"/api/configuration/config-token/automations/{archived_id}/duplicate",
            json={"target_session_id": "new-session"},
        )
        assert duplicated.status_code == 201, duplicated.text
        assert duplicated.json()["session_id"] == "new-session"
        assert duplicated.json()["enabled"] is False

    def test_migrate_legacy_settings(
        self, client, seed_lock_configuration, mock_chaster_api, mongo_db
    ):
        seed_automation_session(
            seed_lock_configuration,
            config={
                "lock_on_freeze": True,
                "unlock_on_unfreeze": True,
                "censorPicsConfig": {
                    "limit_count": 10,
                    "added_duration": 300,
                    "enabled": True,
                },
            },
        )
        mock_chaster_api(
            make_configuration_response(
                role="keyholder", session_id=SESSION_ID
            )
        )

        response = client.post(
            "/api/configuration/config-token/automations/migrate"
        )
        assert response.status_code == 200, response.text
        assert len(response.json()) == 3
        session = mongo_db["users_lock_configurations"].find_one(
            {"session_id": SESSION_ID}
        )
        assert session["automation_mode"] is True


class FakeAutomationRepository:
    def __init__(self, rule: SimpleNamespace):
        self.rule = rule

    async def list_for_session(self, _session_id: str, **_kwargs):
        return [self.rule]

    async def archive_for_session(self, _session_id: str) -> int:
        return 0


class FakeCounterRepository:
    def __init__(self):
        self.documents: list[dict] = []

    async def load_for_session(self, _session_id: str):
        return []

    async def bulk_upsert(self, counters: list[dict]):
        self.documents.extend(counters)

    async def delete_for_session(self, _session_id: str):
        return None


class FakeExecutionRepository:
    async def create(self, fields: dict):
        return SimpleNamespace(id="execution-1", **fields)

    async def update(self, _execution_id: str, **_fields):
        return None


class FakeActions:
    def __init__(self, *, fail: bool = False):
        self.calls: list[list[AutomationActionSchema]] = []
        self.fail = fail

    async def execute(self, actions, context):
        self.calls.append(actions)
        return [
            ActionResult(
                type=action.type,
                status="failed" if self.fail else "success",
                error="Chaster rejected the time penalty" if self.fail else None,
            )
            for action in actions
        ]


class TestAutomationEngine:
    def _engine(self, rule: SimpleNamespace, *, fail: bool = False):
        actions = FakeActions(fail=fail)
        engine = AutomationEngine(
            automations=FakeAutomationRepository(rule),
            counters=FakeCounterRepository(),
            executions=FakeExecutionRepository(),
            actions=actions,
        )
        return engine, actions

    def _rule(self, *, count: int = 2) -> SimpleNamespace:
        return SimpleNamespace(
            id="rule-1",
            session_id=SESSION_ID,
            owner_id=KEYHOLDER_ID,
            owner_role="keyholder",
            name="Eyes and Belly",
            enabled=True,
            priority=100,
            trigger={
                "event": EVENT_PURYFI_MEDIA_SCAN,
                "conditions": [
                    {
                        "field": "labels",
                        "op": "contains_all",
                        "value": ["Eye", "Tummy"],
                    }
                ],
                "count": count,
                "window_seconds": 0,
                "count_mode": "images",
            },
            actions=[
                {"type": "chaster.add_time", "params": {"seconds": 120}}
            ],
            limits={"cooldown_seconds": 0, "max_per_day": 0},
        )

    def _event_rule(
        self,
        event: str,
        conditions: list[dict] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id="event-rule-1",
            session_id=SESSION_ID,
            owner_id=KEYHOLDER_ID,
            owner_role="keyholder",
            name="PuryFi event rule",
            enabled=True,
            priority=100,
            trigger={
                "event": event,
                "conditions": conditions or [],
                "count": 1,
                "window_seconds": 0,
                "count_mode": "images",
            },
            actions=[
                {
                    "type": "chaster.log",
                    "params": {"title": "PuryFi event"},
                }
            ],
            limits={"cooldown_seconds": 0, "max_per_day": 0},
        )

    def test_catalog_exposes_puryfi_protocol_events(self):
        events = {event.type for event in automation_catalog().events}
        assert EVENT_PURYFI_STATE_CHANGED in events
        assert "puryfi.connection.ready" in events
        assert "puryfi.connection.disconnected" in events
        assert "puryfi.user.changed" in events
        assert "puryfi.intents.changed" not in events

    def test_catalog_exposes_chaster_lock_actions(self):
        actions = {action.type for action in automation_catalog().actions}
        assert {
            "chaster.freeze",
            "chaster.unfreeze",
            "chaster.toggle_freeze",
            "chaster.pillory",
            "chaster.set_timer_visibility",
        } <= actions

    def test_event_rule_uses_puryfi_state_context(self):
        async def run():
            rule = self._event_rule(
                EVENT_PURYFI_STATE_CHANGED,
                [
                    {"field": "puryfi_enabled", "op": "eq", "value": False},
                    {"field": "chaster_frozen", "op": "eq", "value": True},
                ],
            )
            engine, actions = self._engine(rule)
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
                chaster_frozen=True,
            )
            await engine.load_session(session)

            assert engine.record_event_nowait(
                session,
                event_type=EVENT_PURYFI_STATE_CHANGED,
                payload={"path": "enabled"},
                context={
                    "puryfi_enabled": False,
                    "puryfi_has_lock": False,
                    "chaster_frozen": True,
                },
            )
            await asyncio.gather(*list(engine._tasks))

            assert len(actions.calls) == 1
            assert actions.calls[0][0].type == "chaster.log"

        asyncio.run(run())

    def test_event_rule_ignores_a_non_matching_context(self):
        async def run():
            rule = self._event_rule(
                EVENT_PURYFI_STATE_CHANGED,
                [{"field": "puryfi_enabled", "op": "eq", "value": False}],
            )
            engine, actions = self._engine(rule)
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
            )
            await engine.load_session(session)

            assert engine.record_event_nowait(
                session,
                event_type=EVENT_PURYFI_STATE_CHANGED,
                context={"puryfi_enabled": True},
            )
            await asyncio.gather(*list(engine._tasks))

            assert actions.calls == []

        asyncio.run(run())

    def test_event_rule_does_not_match_an_unknown_state(self):
        async def run():
            rule = self._event_rule(
                EVENT_PURYFI_STATE_CHANGED,
                [{"field": "puryfi_enabled", "op": "eq", "value": False}],
            )
            engine, actions = self._engine(rule)
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
            )
            await engine.load_session(session)

            assert engine.record_event_nowait(
                session,
                event_type=EVENT_PURYFI_STATE_CHANGED,
                context={"puryfi_enabled": None},
            )
            await asyncio.gather(*list(engine._tasks))

            assert actions.calls == []

        asyncio.run(run())

    def test_counts_matching_images_and_triggers_once(self):
        async def run():
            engine, actions = self._engine(self._rule(count=2))
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
            )
            await engine.load_session(session)
            objects = [
                {"label": 20, "score": 0.9},  # Eye
                {"label": 0, "score": 0.8},   # Tummy
            ]

            assert engine.record_nowait(session, objects) is True
            assert actions.calls == []
            assert engine.record_nowait(session, objects) is True
            await asyncio.sleep(0)
            await asyncio.gather(*list(engine._tasks))

            assert len(actions.calls) == 1
            assert actions.calls[0][0].type == "chaster.add_time"

            # The minimum media cooldown prevents an immediate third trigger.
            assert engine.record_nowait(session, objects) is True
            await asyncio.sleep(0)
            assert len(actions.calls) == 1

        asyncio.run(run())

    def test_failed_time_penalty_restores_the_counter(self):
        async def run():
            engine, actions = self._engine(self._rule(count=2), fail=True)
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
            )
            await engine.load_session(session)
            objects = [
                {"label": 20, "score": 0.9},
                {"label": 0, "score": 0.8},
            ]

            engine.record_nowait(session, objects)
            engine.record_nowait(session, objects)
            await asyncio.sleep(0)
            await asyncio.gather(*list(engine._tasks))

            assert len(actions.calls) == 1
            state = engine._counter_state[(SESSION_ID, "rule-1")]
            assert state.count == 2

        asyncio.run(run())

    def test_disabled_rule_does_not_trigger(self):
        async def run():
            rule = self._rule(count=1)
            rule.enabled = False
            engine, actions = self._engine(rule)
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=True,
            )
            await engine.load_session(session)
            objects = [
                {"label": 20, "score": 0.9},
                {"label": 0, "score": 0.8},
            ]

            assert engine.record_nowait(session, objects) is True
            await asyncio.sleep(0)
            assert actions.calls == []

        asyncio.run(run())

    def test_non_automation_session_does_not_handle_scans(self):
        async def run():
            engine, actions = self._engine(self._rule(count=1))
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                automation_mode=False,
            )
            assert engine.record_nowait(session, []) is False
            assert actions.calls == []

        asyncio.run(run())


class FakeActionSessions:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []

    async def update(self, session_id: str, **fields) -> bool:
        self.updates.append((session_id, fields))
        return True


class FakeActionQueue:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, dict]] = []

    async def enqueue(
        self, link_token: str, msg_type: str, payload: dict
    ) -> None:
        self.messages.append((link_token, msg_type, payload))


class FakeActionRegistry:
    def get(self, _link_token: str):
        return None


class FakeActionChaster:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[tuple[str, tuple, dict]] = []

    async def freeze(self, session_id: str) -> bool:
        self.calls.append(("freeze", (session_id,), {}))
        return self.success

    async def unfreeze(self, session_id: str) -> bool:
        self.calls.append(("unfreeze", (session_id,), {}))
        return self.success

    async def toggle_freeze(self, session_id: str) -> bool:
        self.calls.append(("toggle_freeze", (session_id,), {}))
        return self.success

    async def pillory(
        self,
        session_id: str,
        duration: int,
        *,
        reason: str | None = None,
    ) -> bool:
        self.calls.append(
            ("pillory", (session_id, duration), {"reason": reason})
        )
        return self.success

    async def set_display_remaining_time(
        self, session_id: str, display: bool
    ) -> bool:
        self.calls.append(
            ("set_display_remaining_time", (session_id, display), {})
        )
        return self.success


def make_action_executor(
    session: LockSession,
    *,
    chaster: FakeActionChaster | None = None,
) -> tuple[ActionExecutor, FakeActionSessions, FakeActionQueue]:
    sessions = FakeActionSessions()
    queue = FakeActionQueue()
    executor = ActionExecutor(
        sessions=sessions,  # type: ignore[arg-type]
        chaster=chaster or FakeActionChaster(),  # type: ignore[arg-type]
        puryfi=FakeActionRegistry(),  # type: ignore[arg-type]
        queue=queue,  # type: ignore[arg-type]
    )
    return executor, sessions, queue


class TestPuryfiLockAction:
    def test_lock_reuses_the_stored_password(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                link_token="token-1",
                lock_password="stored-secret",
            )
            executor, sessions, queue = make_action_executor(session)

            result = await executor.execute(
                [
                    AutomationActionSchema(
                        type="puryfi.lock",
                        params={},
                        on_failure="stop",
                    )
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.connection.ready",
                ),
            )

            assert result[0].status == "queued"
            assert sessions.updates == []
            assert queue.messages[0][2]["value"]["password"] == {
                "secret": "stored-secret"
            }

        asyncio.run(run())

    def test_lock_generates_a_password_only_when_none_exists(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
                link_token="token-1",
            )
            executor, sessions, queue = make_action_executor(session)

            result = await executor.execute(
                [
                    AutomationActionSchema(
                        type="puryfi.lock",
                        params={},
                        on_failure="stop",
                    )
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.connection.ready",
                ),
            )

            assert result[0].status == "queued"
            assert session.lock_password
            assert sessions.updates == [
                (SESSION_ID, {"lock_password": session.lock_password})
            ]
            assert queue.messages[0][2]["value"]["password"] == {
                "secret": session.lock_password
            }

        asyncio.run(run())


class TestChasterLockActions:
    def test_freeze_unfreeze_and_toggle_call_the_gateway(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
            )
            chaster = FakeActionChaster()
            executor, _, _ = make_action_executor(session, chaster=chaster)

            results = await executor.execute(
                [
                    AutomationActionSchema(
                        type="chaster.freeze", params={}, on_failure="stop"
                    ),
                    AutomationActionSchema(
                        type="chaster.unfreeze", params={}, on_failure="stop"
                    ),
                    AutomationActionSchema(
                        type="chaster.toggle_freeze",
                        params={},
                        on_failure="stop",
                    ),
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.connection.disconnected",
                ),
            )

            assert [result.status for result in results] == [
                "success",
                "success",
                "success",
            ]
            assert chaster.calls == [
                ("freeze", (SESSION_ID,), {}),
                ("unfreeze", (SESSION_ID,), {}),
                ("toggle_freeze", (SESSION_ID,), {}),
            ]

        asyncio.run(run())

    def test_pillory_passes_duration_and_reason(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
            )
            chaster = FakeActionChaster()
            executor, _, _ = make_action_executor(session, chaster=chaster)

            await executor.execute(
                [
                    AutomationActionSchema(
                        type="chaster.pillory",
                        params={
                            "duration": 300,
                            "reason": "Censored media",
                        },
                        on_failure="stop",
                    )
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.media.scan",
                ),
            )

            assert chaster.calls == [
                (
                    "pillory",
                    (SESSION_ID, 300),
                    {"reason": "Censored media"},
                )
            ]

        asyncio.run(run())

    def test_pillory_ignores_a_blank_reason(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
            )
            chaster = FakeActionChaster()
            executor, _, _ = make_action_executor(session, chaster=chaster)

            await executor.execute(
                [
                    AutomationActionSchema(
                        type="chaster.pillory",
                        params={"duration": 300, "reason": "   "},
                        on_failure="stop",
                    )
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.media.scan",
                ),
            )

            assert chaster.calls[0][2] == {"reason": None}

        asyncio.run(run())

    def test_timer_visibility_passes_the_boolean(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
            )
            chaster = FakeActionChaster()
            executor, _, _ = make_action_executor(session, chaster=chaster)

            await executor.execute(
                [
                    AutomationActionSchema(
                        type="chaster.set_timer_visibility",
                        params={"display_remaining_time": True},
                        on_failure="stop",
                    ),
                    AutomationActionSchema(
                        type="chaster.set_timer_visibility",
                        params={"display_remaining_time": False},
                        on_failure="stop",
                    ),
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="chaster.lock.frozen",
                ),
            )

            assert chaster.calls == [
                ("set_display_remaining_time", (SESSION_ID, True), {}),
                ("set_display_remaining_time", (SESSION_ID, False), {}),
            ]

        asyncio.run(run())

    def test_a_rejected_lock_action_is_reported_as_failed(self):
        async def run():
            session = LockSession(
                session_id=SESSION_ID,
                config=ChasterExtensionConfigSchema(),
            )
            chaster = FakeActionChaster(success=False)
            executor, _, _ = make_action_executor(session, chaster=chaster)

            results = await executor.execute(
                [
                    AutomationActionSchema(
                        type="chaster.freeze", params={}, on_failure="stop"
                    )
                ],
                ActionContext(
                    session=session,
                    event_id="event-1",
                    event_type="puryfi.connection.disconnected",
                ),
            )

            assert results[0].status == "failed"
            assert results[0].error == "Chaster rejected the action"

        asyncio.run(run())


class TestChasterLockActionValidation:
    def test_pillory_requires_a_positive_duration(self):
        with pytest.raises(ValidationError):
            AutomationActionSchema(
                type="chaster.pillory",
                params={"duration": 0},
            )

    def test_pillory_reason_must_be_a_string(self):
        with pytest.raises(ValidationError):
            AutomationActionSchema(
                type="chaster.pillory",
                params={"duration": 300, "reason": 1},
            )

    def test_timer_visibility_requires_a_boolean(self):
        with pytest.raises(ValidationError):
            AutomationActionSchema(
                type="chaster.set_timer_visibility",
                params={"display_remaining_time": "show"},
            )
