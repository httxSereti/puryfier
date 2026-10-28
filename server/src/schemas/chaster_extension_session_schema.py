from pydantic import BaseModel, ConfigDict

from schemas.chaster_extension_configuration_schema import ChasterExtensionConfigSchema


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
    config: ChasterExtensionConfigSchema | None = None

    """
        Emergency Puryfi lock password.
        Cleartext only for the keyholder; null for every other role or if unset.
    """
    lock_password: str | None = None
