"""Domain entities and value objects.

This module is deliberately framework-free: no FastAPI, Beanie, msgpack or
database imports. The API, persistence and realtime layers may depend on these
types, but the reverse must never happen.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PuryfiObjectLabel(IntEnum):
    Tummy = 0
    TummyCovered = 1
    Buttocks = 2
    ButtocksCovered = 3
    FemaleBreast = 4
    FemaleBreastCovered = 5
    FemaleGenitals = 6
    FemaleGenitalsCovered = 7
    MaleGenitalsCovered = 8
    MaleGenitals = 9
    MaleBreast = 10
    MaleBreastCovered = 11
    FemaleFace = 12
    MaleFace = 13
    FootCovered = 14
    Foot = 15
    ArmpitCovered = 16
    Armpit = 17
    AnusCovered = 18
    Anus = 19
    Eye = 20
    Mouth = 21
    NippleCovered = 22
    Nipple = 23
    HandCovered = 24
    Hand = 25
    Silhouette = 26

    @classmethod
    def get_name(cls, value: int) -> str | None:
        try:
            return cls(value).name
        except ValueError:
            return None


class CensorPicsConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    limit_count: int = Field(default=100, ge=1, le=10_000)
    added_duration: int = Field(default=600, ge=1, le=604_800)
    enabled: bool = False


class ChasterExtensionConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lock_on_freeze: bool = False
    unlock_on_unfreeze: bool = False

    censorPicsConfig: CensorPicsConfigSchema = Field(
        default_factory=CensorPicsConfigSchema
    )


class ChasterExtensionConfigurationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str

    # Puryfi connection status
    is_online: bool = False
    has_linked_plugin: bool = False
    puryfi_version: str | None = None
    link_token: str | None = None

    # Chaster extension configuration
    has_session: bool = False
    config: ChasterExtensionConfigSchema | None = None


class ChasterExtensionSessionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str

    # Chaster session information
    role: str

    # Puryfi connection status
    is_online: bool = False
    has_linked_plugin: bool = False
    puryfi_version: str | None = None
    link_token: str | None = None

    # Lock configuration
    config: ChasterExtensionConfigSchema | None = None

    # Emergency Puryfi lock password.
    # Cleartext only for the keyholder; null for every other role or if unset.
    lock_password: str | None = None


@dataclass(slots=True)
class LockSession:
    """A Chaster lock session linked (or linkable) to a Puryfi plugin."""

    session_id: str
    config: ChasterExtensionConfigSchema
    id: str | None = None
    lock_id: str | None = None
    link_token: str | None = None
    has_linked_plugin: bool = False
    keyholder_id: str | None = None
    wearer_id: str | None = None
    puryfi_username: str | None = None
    seen_censored_objects: int = 0
    lock_password: str | None = None


@dataclass(slots=True)
class QueuedCommand:
    """One durable outbound command waiting for a Puryfi connection."""

    id: str
    link_token: str
    msg_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChasterSessionAuth:
    """Parsed payload of Chaster's session-auth endpoint."""

    role: str
    session_id: str
    lock_id: str | None = None
    keyholder_id: str | None = None
    wearer_id: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChasterConfiguration:
    """Parsed payload of Chaster's extension-configuration endpoint."""

    role: str
    session_id: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
