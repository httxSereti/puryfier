from typing import Annotated
from datetime import datetime, timezone
from beanie import Document, Indexed
from pydantic import Field


class User(Document):
    """Mirrors a linked Chaster user."""

    # Chaster user id
    chaster_user_id: Annotated[str, Indexed(unique=True)]

    # Chaster username
    chaster_username: Annotated[str, Indexed(unique=True)]

    # Token used to link Puryfi plugin with Chaster extension
    link_token: str | None = None

    # Whether user has linked Puryfi and Chaster
    is_linked: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "users"

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.chaster_username!r}>"
