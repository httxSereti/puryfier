from pydantic import BaseModel, ConfigDict


class ChasterExtensionSessionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str

    """
        Chaster session information
    """
    role: str

    """
        Puryfi connection status
    """
    is_online: bool = False
    has_linked_plugin: bool = False
    link_token: str | None = None

    """
        Lock configuration
    """
    lock_on_freeze: bool = False
    lock_password: str | None = None
    unlock_on_unfreeze: bool = False