"""Deprecated import path. Use :mod:`infra.documents`."""

from infra.documents import (
    QueuedMessage,
    UserLockConfiguration,
    WebhookInboxEntry,
)

__all__ = ["QueuedMessage", "UserLockConfiguration", "WebhookInboxEntry"]
