from typing import Annotated
from beanie import Document, Indexed
from schemas import ChasterExtensionConfigSchema


class UserLockConfiguration(Document):
    """Persistent per-session configuration linking a Chaster lock to Puryfi."""

    # Chaster lock identifier
    lock_id: Annotated[str, Indexed()] | None = None

    # Chaster session identifier
    session_id: Annotated[str, Indexed()] | None = None

    # Token used to link the Puryfi plugin with the Chaster extension
    link_token: Annotated[str, Indexed(unique=True)] | None = None

    # Whether the Puryfi plugin is actively linked to this lock
    has_linked_plugin: bool = False

    # Chaster user id of the keyholder
    keyholder_id: str | None = None

    # Chaster user id of the wearer
    wearer_id: str | None = None

    # Puryfi username
    puryfi_username: str | None = None

    # Configurations
    lock_password: str | None = None
    config: ChasterExtensionConfigSchema

    class Settings:
        name = "users_lock_configurations"

    def __repr__(self) -> str:
        return (
            f"<UserLockConfiguration id={self.id!r} "
            f"lock_id={self.lock_id!r} has_linked_plugin={self.has_linked_plugin}>"
        )
