"""Composition root for the current process.

Until the application moves dependencies to ``app.state`` (P2 #2), the API
routes, workers and realtime layer share these singletons.
"""

from infra.chaster import ChasterService
from infra.queue import MongoMessageQueue
from infra.repositories import MongoLockSessionRepository
from realtime.registry import manager
from realtime.watchers import watchers

chaster_gateway = ChasterService()
session_repository = MongoLockSessionRepository()
message_queue = MongoMessageQueue()
puryfi_registry = manager
session_watchers = watchers
