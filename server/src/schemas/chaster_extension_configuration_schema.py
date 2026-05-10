from typing import Any
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ChasterExtensionConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lock_on_freeze: bool = False
    unlock_on_unfreeze: bool = False

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