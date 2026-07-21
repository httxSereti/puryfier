"""In-memory async MongoDB stand-in for e2e API tests (no Docker required).

Bridges mongomock's synchronous client to the subset of the pymongo *async*
API surface that beanie 2.x uses, so the real application (FastAPI + beanie
documents) can run in tests without a MongoDB server.

Caveats:
- TTL indexes are accepted but expiry is NOT simulated.
- Transactions/change streams/advanced aggregations are out of scope; if an
  endpoint ever needs those, point `DATABASE_URL` at a real Mongo for that
  test instead.
"""

from __future__ import annotations

import functools
import inspect

import mongomock


def _call_compat(func, *args, **kwargs):
    """Call a mongomock method, dropping pymongo-only kwargs it doesn't accept
    (e.g. session, authorizedCollections)."""
    kwargs.pop("session", None)
    params = inspect.signature(func).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    return func(*args, **kwargs)


def _strip_session(kwargs: dict) -> dict:
    # mongomock has no real session support; pymongo passes session=None.
    kwargs.pop("session", None)
    return kwargs


class _AsyncCursor:
    """Duck-typed pymongo AsyncCursor over a mongomock cursor."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._iterator = None

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, count):
        self._cursor = self._cursor.skip(count)
        return self

    def limit(self, count):
        self._cursor = self._cursor.limit(count)
        return self

    async def to_list(self, length=None):
        docs = list(self._cursor)
        return docs if length is None else docs[:length]

    def __aiter__(self):
        self._iterator = iter(self._cursor)
        return self

    async def __anext__(self):
        if self._iterator is None:
            self._iterator = iter(self._cursor)
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class _AsyncCollection:
    """Duck-typed pymongo AsyncCollection over a mongomock collection.

    `find`/`aggregate` stay synchronous and return a cursor wrapper; every
    other method is exposed as an awaitable via __getattr__.
    """

    def __init__(self, collection):
        self._collection = collection

    def find(self, *args, **kwargs):
        return _AsyncCursor(self._collection.find(*args, **_strip_session(kwargs)))

    def aggregate(self, *args, **kwargs):
        return _AsyncCursor(self._collection.aggregate(*args, **_strip_session(kwargs)))

    def __getattr__(self, name):
        attr = getattr(self._collection, name)
        if not callable(attr):
            return attr

        @functools.wraps(attr)
        async def awaitable(*args, **kwargs):
            return _call_compat(attr, *args, **kwargs)

        return awaitable


class _AsyncDatabase:
    """Duck-typed pymongo AsyncDatabase over a mongomock database."""

    def __init__(self, database):
        self._database = database

    async def command(self, command, **kwargs):
        # beanie's initializer fetches buildInfo for feature detection;
        # mongomock only implements `ping`.
        if isinstance(command, str):
            command = {command: 1}
        if "buildInfo" in command or "buildinfo" in command:
            return {"version": "8.0.0", "versionArray": [8, 0, 0, 0], "ok": 1.0}
        return self._database.command(command, **kwargs)

    def __getitem__(self, name):
        return _AsyncCollection(self._database[name])

    def get_collection(self, name, **kwargs):
        return _AsyncCollection(self._database.get_collection(name))

    def __getattr__(self, name):
        attr = getattr(self._database, name)
        if not callable(attr):
            return attr

        @functools.wraps(attr)
        async def awaitable(*args, **kwargs):
            return _call_compat(attr, *args, **kwargs)

        return awaitable


class InMemoryMongoClient:
    """Drop-in replacement for pymongo.AsyncMongoClient backed by mongomock.

    The wrapped synchronous client is exposed as `sync_client` so tests can
    seed and assert against the very same in-memory store the app uses.
    """

    def __init__(self):
        self.sync_client = mongomock.MongoClient()

    def __getitem__(self, name) -> _AsyncDatabase:
        return _AsyncDatabase(self.sync_client[name])

    def get_database(self, name, **kwargs) -> _AsyncDatabase:
        return _AsyncDatabase(self.sync_client.get_database(name))

    def close(self):
        # db.py calls close() synchronously; nothing to release here.
        pass
