from typing import Optional
from pydantic import BaseModel, ConfigDict

class CensorPicsConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    limit_count: int = 100
    added_duration: int = 600
    enabled: bool = False

class ChasterExtensionConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lock_on_freeze: bool = False
    unlock_on_unfreeze: bool = False
    
    censorPicsConfig: CensorPicsConfigSchema = CensorPicsConfigSchema()

class ChasterExtensionConfigurationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str

    """
        Puryfi connection status
    """
    is_online: bool = False
    has_linked_plugin: bool = False
    link_token: Optional[str] = None

    """
        Chaster extension configuration
    """
    has_session: bool = False
    config: Optional[ChasterExtensionConfigSchema] = None