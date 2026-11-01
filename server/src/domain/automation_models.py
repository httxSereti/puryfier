"""Automation rules: triggers, conditions, actions and API schemas.

Automations are deliberately declarative. They are stored as data, validated
at the API boundary, compiled by the rule engine, and executed by the action
executor. No user-provided code is ever executed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.entities import PuryfiObjectLabel

AUTOMATION_SCHEMA_VERSION = 1

EVENT_CHASTER_SESSION_JOINED = "chaster.session.joined"
EVENT_CHASTER_SESSION_LEFT = "chaster.session.left"
EVENT_CHASTER_LOCK_FROZEN = "chaster.lock.frozen"
EVENT_CHASTER_LOCK_UNFROZEN = "chaster.lock.unfrozen"
EVENT_CHASTER_SESSION_DELETED = "chaster.session.deleted"
EVENT_PURYFI_MEDIA_SCAN = "puryfi.media.scan"
EVENT_PURYFI_CONNECTION_READY = "puryfi.connection.ready"
EVENT_PURYFI_CONNECTION_DISCONNECTED = "puryfi.connection.disconnected"
EVENT_PURYFI_STATE_CHANGED = "puryfi.state.changed"

SUPPORTED_EVENTS = (
    EVENT_CHASTER_SESSION_JOINED,
    EVENT_CHASTER_SESSION_LEFT,
    EVENT_CHASTER_LOCK_FROZEN,
    EVENT_CHASTER_LOCK_UNFROZEN,
    EVENT_PURYFI_MEDIA_SCAN,
)

EVENT_LABELS = {
    EVENT_CHASTER_SESSION_JOINED: "Chaster session joined",
    EVENT_CHASTER_SESSION_LEFT: "Chaster session left",
    EVENT_CHASTER_LOCK_FROZEN: "Chaster lock frozen",
    EVENT_CHASTER_LOCK_UNFROZEN: "Chaster lock unfrozen",
    EVENT_CHASTER_SESSION_DELETED: "Chaster session deleted",
    EVENT_PURYFI_MEDIA_SCAN: "Image analysed by PuryFi",
    EVENT_PURYFI_CONNECTION_READY: "PuryFi connected",
    EVENT_PURYFI_CONNECTION_DISCONNECTED: "PuryFi disconnected",
    EVENT_PURYFI_STATE_CHANGED: "PuryFi state changed",
}

# Human-readable names for the SDK labels. The canonical value stored in a
# condition is the PuryfiObjectLabel member name (for example "Eye").
LABEL_DISPLAY_NAMES: dict[str, str] = {
    "Tummy": "Belly",
    "TummyCovered": "Belly (covered)",
    "Buttocks": "Buttocks",
    "ButtocksCovered": "Buttocks (covered)",
    "FemaleBreast": "Breasts",
    "FemaleBreastCovered": "Breasts (covered)",
    "FemaleGenitals": "Female genitals",
    "FemaleGenitalsCovered": "Female genitals (covered)",
    "MaleGenitalsCovered": "Male genitals (covered)",
    "MaleGenitals": "Male genitals",
    "MaleBreast": "Male chest",
    "MaleBreastCovered": "Male chest (covered)",
    "FemaleFace": "Female face",
    "MaleFace": "Male face",
    "FootCovered": "Feet (covered)",
    "Foot": "Feet",
    "ArmpitCovered": "Armpits (covered)",
    "Armpit": "Armpits",
    "AnusCovered": "Anus (covered)",
    "Anus": "Anus",
    "Eye": "Eyes",
    "Mouth": "Mouth",
    "NippleCovered": "Nipples (covered)",
    "Nipple": "Nipples",
    "HandCovered": "Hands (covered)",
    "Hand": "Hands",
    "Silhouette": "Silhouette",
}

# Labels that the legacy "censored media" feature considers censorable.
LEGACY_CENSORABLE_LABELS = (
    "Buttocks",
    "FemaleBreast",
    "FemaleGenitals",
    "MaleGenitals",
    "Anus",
    "Nipple",
)

CONDITION_FIELDS = (
    "labels",
    "score",
    "object_count",
    "chaster_frozen",
    "puryfi_enabled",
    "puryfi_has_lock",
)

CONDITION_OPERATORS = (
    "contains_all",
    "contains_any",
    "not_contains",
    "gte",
    "lte",
    "eq",
    "neq",
)

ACTION_TYPES = (
    "puryfi.enable",
    "puryfi.disable",
    "puryfi.lock",
    "puryfi.unlock",
    "puryfi.set_lock",
    "puryfi.enter_emergency_token",
    "chaster.add_time",
    "chaster.remove_time",
    "chaster.log",
)


class AutomationConditionSchema(BaseModel):
    """One condition evaluated against a normalized event payload."""

    model_config = ConfigDict(extra="forbid")

    field: str
    op: str
    value: Any = None

    @model_validator(mode="after")
    def _validate_field_and_operator(self) -> AutomationConditionSchema:
        if self.field not in CONDITION_FIELDS:
            raise ValueError(f"Unsupported condition field: {self.field}")
        if self.op not in CONDITION_OPERATORS:
            raise ValueError(f"Unsupported condition operator: {self.op}")
        return self


class AutomationTriggerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str
    conditions: list[AutomationConditionSchema] = Field(default_factory=list)
    # Baseline confidence for media rules. A rule can still add a stricter
    # `score` condition for advanced use cases.
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    count: int = Field(default=1, ge=1, le=10_000)
    window_seconds: int = Field(default=0, ge=0, le=86_400)
    count_mode: Literal["images", "objects"] = "images"

    @model_validator(mode="after")
    def _validate_event(self) -> AutomationTriggerSchema:
        if self.event not in EVENT_LABELS:
            raise ValueError(f"Unsupported event: {self.event}")
        return self


class AutomationActionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    on_failure: Literal["stop", "continue"] = "stop"

    @model_validator(mode="after")
    def _validate_action(self) -> AutomationActionSchema:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"Unsupported action: {self.type}")

        if self.type in {"chaster.add_time", "chaster.remove_time"}:
            seconds = self.params.get("seconds")
            if (
                isinstance(seconds, bool)
                or not isinstance(seconds, int)
                or seconds <= 0
                or seconds > 604_800
            ):
                raise ValueError(
                    f"{self.type} requires an integer seconds value "
                    "between 1 and 604800"
                )
        elif self.type == "chaster.log":
            title = self.params.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("chaster.log requires a non-empty title")
        elif self.type == "puryfi.set_lock":
            password = self.params.get("password")
            if not isinstance(password, str) or not password:
                raise ValueError("puryfi.set_lock requires a password")
        elif self.type == "puryfi.enter_emergency_token":
            token = self.params.get("token")
            if not isinstance(token, str) or not token:
                raise ValueError(
                    "puryfi.enter_emergency_token requires a token"
                )
        return self


class AutomationLimitsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cooldown_seconds: int = Field(default=0, ge=0, le=604_800)
    max_per_day: int = Field(default=0, ge=0, le=1_000)


class AutomationCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10_000)
    trigger: AutomationTriggerSchema
    actions: list[AutomationActionSchema] = Field(min_length=1, max_length=10)
    limits: AutomationLimitsSchema = Field(default_factory=AutomationLimitsSchema)


class AutomationUpdateSchema(BaseModel):
    """Partial update. A non-owner keyholder may only change ``enabled``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    trigger: AutomationTriggerSchema | None = None
    actions: list[AutomationActionSchema] | None = Field(
        default=None, min_length=1, max_length=10
    )
    limits: AutomationLimitsSchema | None = None


class AutomationDuplicateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_session_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=120)


class AutomationTestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: dict[str, Any] | None = None


class AutomationActionParamCatalogSchema(BaseModel):
    key: str
    label: str
    type: Literal["number", "text", "boolean", "json"]
    required: bool = False
    default: Any = None
    min: int | None = None
    max: int | None = None
    help: str | None = None


class AutomationActionCatalogSchema(BaseModel):
    type: str
    label: str
    description: str
    params: list[AutomationActionParamCatalogSchema] = Field(default_factory=list)


class AutomationEventCatalogSchema(BaseModel):
    type: str
    label: str
    description: str
    supports_count: bool = False


class AutomationLabelCatalogSchema(BaseModel):
    value: str
    label: str
    censorable: bool = False


class AutomationCatalogSchema(BaseModel):
    events: list[AutomationEventCatalogSchema]
    actions: list[AutomationActionCatalogSchema]
    labels: list[AutomationLabelCatalogSchema]


class AutomationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    lock_id: str | None = None
    lock_label: str | None = None
    owner_id: str
    owner_role: str
    name: str
    status: str = "active"
    enabled: bool = True
    priority: int = 100
    trigger: AutomationTriggerSchema
    actions: list[AutomationActionSchema]
    limits: AutomationLimitsSchema
    source_automation_id: str | None = None
    disabled_by: str | None = None
    disabled_by_role: str | None = None
    disabled_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # UI permissions, computed for the requesting actor.
    is_owner: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_disable: bool = False


class AutomationTargetSchema(BaseModel):
    session_id: str
    lock_id: str | None = None
    lock_label: str | None = None
    role: str


class AutomationExecutionSchema(BaseModel):
    id: str
    session_id: str
    automation_id: str
    automation_name: str | None = None
    event_id: str
    event_type: str
    status: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AutomationListSchema(BaseModel):
    session_id: str | None = None
    role: str
    owner_id: str | None = None
    automation_mode: bool = False
    wearer_can_manage: bool = False
    effective_wearer_can_manage: bool = False
    automations: list[AutomationSchema] = Field(default_factory=list)
    archived_automations: list[AutomationSchema] = Field(default_factory=list)
    targets: list[AutomationTargetSchema] = Field(default_factory=list)
    executions: list[AutomationExecutionSchema] = Field(default_factory=list)


class AutomationTestResultSchema(BaseModel):
    matched: bool
    reason: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)


def label_catalog() -> list[AutomationLabelCatalogSchema]:
    censorable = set(LEGACY_CENSORABLE_LABELS)
    return [
        AutomationLabelCatalogSchema(
            value=label.name,
            label=LABEL_DISPLAY_NAMES.get(label.name, label.name),
            censorable=label.name in censorable,
        )
        for label in PuryfiObjectLabel
    ]


def automation_catalog() -> AutomationCatalogSchema:
    return AutomationCatalogSchema(
        events=[
            AutomationEventCatalogSchema(
                type=EVENT_CHASTER_SESSION_JOINED,
                label="Chaster session joined",
                description=(
                    "Runs when the extension session is created for a lock, "
                    "for example when the user joins the lock."
                ),
            ),
            AutomationEventCatalogSchema(
                type=EVENT_CHASTER_SESSION_LEFT,
                label="Chaster session left",
                description=(
                    "Runs when the extension session is deleted, for example "
                    "when the user leaves the lock."
                ),
            ),
            AutomationEventCatalogSchema(
                type=EVENT_CHASTER_LOCK_FROZEN,
                label="Chaster lock frozen",
                description="Runs when the Chaster lock is frozen.",
            ),
            AutomationEventCatalogSchema(
                type=EVENT_CHASTER_LOCK_UNFROZEN,
                label="Chaster lock unfrozen",
                description="Runs when the Chaster lock is unfrozen.",
            ),
            AutomationEventCatalogSchema(
                type=EVENT_PURYFI_MEDIA_SCAN,
                label="Image analysed by PuryFi",
                description=(
                    "Runs for each image scanned by PuryFi. Conditions can match "
                    "labels and detection scores."
                ),
                supports_count=True,
            ),
        ],
        actions=[
            AutomationActionCatalogSchema(
                type="puryfi.lock",
                label="Lock PuryFi with a generated password",
                description=(
                    "Creates a new PuryFi lock password, stores it for the "
                    "keyholder, and applies the lock configuration."
                ),
                params=[
                    AutomationActionParamCatalogSchema(
                        key="timer_seconds",
                        label="Timer (seconds)",
                        type="number",
                        min=1,
                        max=604_800,
                        help="Optional PuryFi timer. Leave empty for no timer.",
                    )
                ],
            ),
            AutomationActionCatalogSchema(
                type="puryfi.enable",
                label="Enable PuryFi",
                description="Turns PuryFi on.",
            ),
            AutomationActionCatalogSchema(
                type="puryfi.unlock",
                label="Unlock PuryFi with the stored password",
                description=(
                    "Enters the emergency password saved when PuryFi was locked."
                ),
            ),
            AutomationActionCatalogSchema(
                type="puryfi.disable",
                label="Disable PuryFi",
                description="Turns PuryFi off.",
            ),
            AutomationActionCatalogSchema(
                type="chaster.add_time",
                label="Add time to the Chaster lock",
                description="Adds seconds to the Chaster lock.",
                params=[
                    AutomationActionParamCatalogSchema(
                        key="seconds",
                        label="Seconds",
                        type="number",
                        required=True,
                        min=1,
                        max=604_800,
                    )
                ],
            ),
            AutomationActionCatalogSchema(
                type="chaster.remove_time",
                label="Remove time from the Chaster lock",
                description="Removes seconds from the Chaster lock.",
                params=[
                    AutomationActionParamCatalogSchema(
                        key="seconds",
                        label="Seconds",
                        type="number",
                        required=True,
                        min=1,
                        max=604_800,
                    )
                ],
            ),
            AutomationActionCatalogSchema(
                type="chaster.log",
                label="Write a Chaster log",
                description="Creates a custom log visible in the lock history.",
                params=[
                    AutomationActionParamCatalogSchema(
                        key="title",
                        label="Title",
                        type="text",
                        required=True,
                    ),
                    AutomationActionParamCatalogSchema(
                        key="description",
                        label="Description",
                        type="text",
                    ),
                ],
            ),
        ],
        labels=label_catalog(),
    )
