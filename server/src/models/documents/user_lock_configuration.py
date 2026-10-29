from typing import ClassVar

from beanie import Document
from pymongo import ASCENDING, IndexModel

from schemas import ChasterExtensionConfigSchema


class UserLockConfiguration(Document):
    """Persistent per-session configuration linking a Chaster lock to Puryfi."""

    # Chaster session identifier (one configuration per session)
    session_id: str

    # Chaster lock identifier
    lock_id: str | None = None

    # Token used to link the Puryfi plugin with the Chaster extension
    link_token: str | None = None

    # Whether the Puryfi plugin is actively linked to this lock
    has_linked_plugin: bool = False

    # Chaster user id of the keyholder
    keyholder_id: str | None = None

    # Chaster user id of the wearer
    wearer_id: str | None = None

    # Puryfi username
    puryfi_username: str | None = None

    # Number of censored media scans since the last successful time penalty.
    # Persisted so reconnects/restarts do not lose progress.
    seen_censored_objects: int = 0

    # Configurations
    # Conscious decision (REVIEW.md #13): lock_password is stored in cleartext
    # because it must be retrievable to send to the Puryfi client on
    # freeze/unfreeze. This is a shared secret for a self-hosted local app;
    # it is never logged and only ever returned to the keyholder role.
    lock_password: str | None = None
    config: ChasterExtensionConfigSchema

    class Settings:
        name = "users_lock_configurations"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel([("lock_id", ASCENDING)]),
            # Partial index: unique only for configurations that actually have
            # a link token. A plain sparse/unique index would still index
            # explicit nulls and reject multiple unlinked configurations.
            IndexModel(
                [("link_token", ASCENDING)],
                unique=True,
                partialFilterExpression={"link_token": {"$type": "string"}},
            ),
        ]

    def __repr__(self) -> str:
        return (
            f"<UserLockConfiguration id={self.id!r} "
            f"lock_id={self.lock_id!r} has_linked_plugin={self.has_linked_plugin}>"
        )
