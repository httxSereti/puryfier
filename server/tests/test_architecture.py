"""Architecture guardrails for the api/domain/infra/realtime/workers split."""

import ast
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[1] / "src" / "domain"

FORBIDDEN_DOMAIN_IMPORTS = {
    "api",
    "beanie",
    "bson",
    "container",
    "fastapi",
    "httpx",
    "infra",
    "models",
    "msgpack",
    "pymongo",
    "realtime",
    "routes",
    "services",
    "typings",
    "utils",
    "workers",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_domain_is_framework_free() -> None:
    """The domain layer must not depend on transport, persistence or adapters."""
    violations: dict[str, set[str]] = {}

    for path in DOMAIN_ROOT.rglob("*.py"):
        forbidden = _imported_roots(path) & FORBIDDEN_DOMAIN_IMPORTS
        if forbidden:
            violations[str(path.relative_to(DOMAIN_ROOT))] = forbidden

    assert violations == {}


def test_legacy_paths_alias_the_new_modules() -> None:
    """The old module paths stay valid while the refactor settles."""
    import api.realtime as canonical_realtime
    import db as legacy_db
    import infra.chaster as canonical_chaster_api
    import infra.mongo as canonical_db
    import models.connection as legacy_connection
    import realtime.connection as canonical_connection
    import routes.websocket as legacy_websocket
    import utils.chaster_api as legacy_chaster_api

    assert legacy_db is canonical_db
    assert legacy_connection is canonical_connection
    assert legacy_websocket is canonical_realtime
    assert legacy_chaster_api is canonical_chaster_api


def test_domain_use_case_can_run_with_fake_ports() -> None:
    """Use cases depend on protocols, not on Mongo or FastAPI."""
    import asyncio

    from domain.entities import ChasterExtensionConfigSchema, LockSession
    from domain.use_cases.lock_events import handle_lock_frozen

    class FakeSessions:
        def __init__(self) -> None:
            self.session = LockSession(
                session_id="session-1",
                config=ChasterExtensionConfigSchema(lock_on_freeze=True),
                id="config-1",
                link_token="token-1",
            )
            self.updates: list[dict] = []

        async def get_by_session_id(self, _session_id: str):
            return self.session

        async def update(self, _session_id: str, **fields):
            self.updates.append(fields)
            return True

    class FakeQueue:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str, dict]] = []

        async def enqueue(self, link_token: str, msg_type: str, payload: dict):
            self.messages.append((link_token, msg_type, payload))

    class FakeRegistry:
        def get(self, _link_token: str):
            return None

    sessions = FakeSessions()
    queue = FakeQueue()
    payload = {
        "event": "action_log.created",
        "requestId": "req-1",
        "data": {
            "sessionId": "session-1",
            "actionLog": {"type": "lock_frozen"},
        },
    }

    result = asyncio.run(
        handle_lock_frozen(
            payload,
            sessions=sessions,  # type: ignore[arg-type]
            queue=queue,  # type: ignore[arg-type]
            puryfi=FakeRegistry(),  # type: ignore[arg-type]
        )
    )

    assert result == {"status": "ok", "action": "lock_frozen_queued_no_connection"}
    assert sessions.updates and sessions.updates[0]["lock_password"]
    assert len(queue.messages) == 2
