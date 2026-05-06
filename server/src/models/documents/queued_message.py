from typing import Any, Annotated
from beanie import Document, Indexed


class QueuedMessage(Document):
    """A message queued for delivery when a Puryfi connection comes online."""

    link_token: Annotated[str, Indexed()]
    msg_type: str
    payload: dict[str, Any]

    class Settings:
        name = "queued_messages"
