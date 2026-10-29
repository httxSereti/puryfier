
from pydantic import BaseModel, ConfigDict, Field


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

    """
        Puryfi connection status
    """
    is_online: bool = False
    has_linked_plugin: bool = False
    link_token: str | None = None

    """
        Chaster extension configuration
    """
    has_session: bool = False
    config: ChasterExtensionConfigSchema | None = None