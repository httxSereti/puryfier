# Code Review — Puryfier (puryfi-chaster-linker)

**Stated assumptions** (context I don't have): this is a self-hosted, single-instance hobby project with a small user base; the keyholder is a semi-trusted party but the wearer owns the Puryfi client; Chaster webhooks only support HTTP Basic auth on the callback URL. Where severity depends on scale, it is noted.

---

## Overall assessment

This is a solid **prototype that is not yet production-ready**. The architecture is sensible and the feature set mostly hangs together, but there are two outright broken features (webhook authentication is dead code; the emergency password never reaches the UI), a broken production frontend build, and a pattern of blocking I/O in an async server that will hurt the moment more than a handful of users are active. Nothing here is unfixable — most issues are a few lines each — but shipping as-is would mean shipping an unauthenticated webhook and a frontend that can't find its backend.

---

## Strengths

- **Clean layering.** `routes / services / models / schemas / typings` is a sensible separation for a project this size. Webhook action handlers are split per-event (`lock_frozen.py`, `lock_unfrozen.py`) with a package-level `__init__` re-export — easy to extend.
- **Offline message queue.** Persisting `setState` messages to Mongo (`QueuedMessage`) when the Puryfi client isn't connected, then draining on reconnect, is genuinely good design for this problem domain. Many people would have just dropped those events.
- **Request/response correlation over the WebSocket.** The `responseId` + `pending_requests` future pattern in `Connection` is the right way to do RPC over a message socket.
- **Deployability story.** `docker-compose` with Traefik, LE DNS challenge, internal-only Mongo network, `.env.example` files, and real `.env` files correctly gitignored. The README quickstart is accurate and complete.
- **Sensible data modeling.** Beanie documents with appropriate indexes (`link_token` unique-indexed, `session_id` indexed); timezone-aware datetimes; pydantic v2 throughout; TS types mirroring API shapes on the frontend.
- **Security intent is visible.** `secrets.compare_digest` for webhook creds, `secrets.token_urlsafe` for lock passwords, hiding the lock password from the wearer role — the *instincts* are right even where the execution has gaps (below).
- **Frontend craft.** Reasonable component decomposition (pages → session/configuration sections → shared `ConfigurationSwitch`), iframe-resizer integration, loading/error states handled explicitly, refs used correctly to keep the message listener closure fresh.

---

## Weaknesses

### Critical

1. **Webhook endpoint is unauthenticated** — *(security, correctness)*. `routes/webhooks/chaster.py` defines `verify_credentials()` and then never uses it. The route depends on `Depends(security)` (which only *parses* the Basic header — any username/password passes, and FastAPI auto-401s only when the header is absent). Anyone on the internet who finds the URL can inject fake `lock_frozen` / `lock_unfrozen` events and toggle users' Puryfi locks at will. This is the single worst bug in the repo because the file *looks* secured.

2. **Emergency lock password never reaches the frontend** — *(correctness)*. In `routes/extensions.py`, `fetch_session` and `create_link_token` pass `lock_password=...`, `lock_on_freeze=...`, `unlock_on_unfreeze=...` into `ChasterExtensionSessionSchema(...)` — but that schema declares none of those fields. Pydantic v2's default `extra="ignore"` silently drops them, and `response_model` would strip them anyway. So `session.lock_password` in the UI is always `undefined`, `ShowPuryfiPassword` never renders, and the careful "HIDDEN"-for-wearer logic is dead code. The keyholder *cannot* retrieve the emergency password — a safety-relevant feature of an app that physically locks things is silently broken. This class of bug (silently swallowed kwargs) is exactly why "type the constructor call" matters.

3. **Production frontend build has no backend URL** — *(deployment correctness)*. `docker-compose.yml` passes `VITE_BACKEND_URL`, `VITE_PURYFI_WS_URL`, `VITE_APP_VERSION` as **runtime `environment:`** on the `front` service. Vite inlines `import.meta.env.*` at **build time**; the `front/Dockerfile` only declares `ARG VITE_BACKEND_URL` (not the other two), and compose never passes `build.args`. Result: the deployed bundle has `VITE_BACKEND_URL === undefined` and every API call hits `undefined/api/...`. This can't have ever worked in the documented deployment path.

### Moderate

4. **Blocking `requests` calls inside async handlers** — *(performance)*. `configuration.py`, `extensions.py`, `services/chaster.py`, `utils/chaster_api.py` all use synchronous `requests` inside `async def` endpoints — including `add_time_to_lock()` called from the WebSocket message handler on every censored-media event. Each call stalls the entire event loop for the duration of a cross-continent HTTPS round-trip (100–500ms+), which also freezes all open WebSocket handling. At the assumed scale this manifests as random UI latency; at any real concurrency it serializes the whole server.

5. **No timeout or cleanup on WebSocket RPC futures** — *(correctness, robustness)*. `Connection.send_message` does `return await future` with no timeout. If the Puryfi client never answers (crash, network drop mid-request, unsupported message), the future hangs forever: `handle_lock_unfrozen` hangs → the Chaster webhook request hangs → Chaster retries → duplicate events. `pending_requests` entries also leak, and on disconnect nothing fails the outstanding futures.

6. **WebSocket lifecycle leaks stale connections** — *(correctness)*. In `routes/websocket.py`: the socket is `accept()`ed *before* the token is validated, and on unknown token the handler just `return`s without `close(code=...)`; `manager.remove()` only happens in the `WebSocketDisconnect` branch — any other exception (e.g. a malformed msgpack frame raising in `handle_message`) propagates and leaves the dead connection registered forever, so `is_online` lies and future sends throw. Needs `try/finally`.

7. **No origin validation on `postMessage`; sends use `"*"`** — *(security)*. `Configuration.tsx` accepts `message` events from any origin and acts on `type === "chaster" && event === "partner_configuration_save"` by PUTting config to the backend. Any window that can get a reference to the iframe (or any script injected into the host page) can trigger saves. Outbound posts also use `"*"` as target origin. Check `e.origin === "https://chaster.app"` (and pass it as targetOrigin).

8. **`POST /api/session/{id}/link-token` has no authorization** — *(security)*. Anyone who learns a `UserLockConfiguration` document id can mint/retrieve that session's link token, connect their own Puryfi client, and steal the connection slot (the `ConnectionManager` silently overwrites on re-`add`). Relatedly, `GET /api/session/{main_token}` returns `link_token` to **both** roles — only the lock password is role-gated. Maybe acceptable in the assumed trust model (the keyholder is semi-trusted), but then the wearer's client can be hijacked by design. Decide consciously and enforce.

9. **Queue draining is lossy and unordered** — *(correctness)*. `fetch_and_delete_queued_messages` reads all, then deletes all, *then* the caller sends them — a crash between delete and send loses messages. Worse, `process_queued_messages` fires each message via `asyncio.create_task(...)`, so delivery order of a sequence like `enterLockPassword` → `setState(enabled=false)` is not guaranteed; for a lock/unlock protocol, ordering is semantic. Also no TTL index and no cap, so the queue grows unboundedly for users who never reconnect.

10. **Webhook handling is not idempotent** — *(correctness)*. Chaster retries webhooks; `requestId` is logged but never stored/deduped. A retried `lock_frozen` **regenerates a new password** and re-sends/re-queues `setState` with it — harmless today only by accident (the DB write happens to keep things consistent), but it's a landmine.

11. **`staticMediaScan` counting doesn't match the feature's description** — *(correctness)*. `seen_censored_objects += 1` fires once per scan *message* whenever `len(objects) > 0`, regardless of how many objects were detected or **what** they are — the label filtering using `PuryfiObjectLabel` is commented out, so a detected *face* or *hand* counts toward "censored pics → add time". Either the label filter or the counting unit (objects vs. scans) needs fixing; right now the "add time when media is censored" feature triggers on things that aren't censored media.

12. **Init/queue race on connect** — *(correctness)*. On `ready`, `initialize_plugin()` (which requests intents) and `process_queued_messages()` run concurrently. Queued `setState` messages requiring intents will fail with `missingPluginIntents`, get requeued, re-trigger `requestPluginIntents`… possible churn loop, plus duplicate intent prompts. Drain the queue *after* `intents_granted_event` is set.

13. **Plaintext password at rest + sensitive data in logs** — *(security/privacy)*. `lock_password` is stored in cleartext in Mongo (no `SECRET`-wrapping; arguably acceptable for a "shared secret to a local app" but should be a conscious decision), and `pprint(data)` dumps full Chaster session payloads — including user objects and config — to stdout in `fetch_session` and the webhook handler. `print`/`pprint` is also the only logging: no levels, no redaction, no timestamps.

14. **CORS misconfiguration** — *(security)*. `allow_origins=["*"]` with `allow_credentials=True` is an invalid combination per the CORS spec (browsers reject it) and signals "I didn't think about CORS." The exact frontend origin is known (`FRONT_URL` is right there in the env) — allowlist it.

15. **`SessionSettings.tsx` binds the wrong field** — *(UI correctness)*. The input labeled "Every {limit_count} images add" is bound to `censorPicsConfig.added_duration` — the same field as the second input. `limit_count` is displayed in the label but never editable/viewable as a value. Copy-paste bug.

16. **Frontend/backend contract drift** — *(correctness)*. Server declares `config: Optional[ChasterExtensionConfigSchema]`; frontend `types/api.ts` declares `config` as required and `SessionSettings` dereferences `session.config.lock_on_freeze` unguarded → runtime `TypeError` if config is ever null. Same class of drift as issue #2 — the two sides are maintained by hand and have already diverged twice.

### Minor

17. **Dead/misleading code** — *(maintainability)*: `User` document registered in Beanie but never used anywhere; `verify_credentials` (see #1); `cuid` instantiated in `configuration.py` but unused; `PuryfiObjectLabel` imported for commented-out code; `ChasterExtensionConfigSchema` imported unused in `configuration.py`; unreachable trailing `return` in `lock_frozen.py`; `create_link_token` passes kwargs the schema drops (misleading even once #2 is fixed); module-level `developer_token` in `configuration.py` re-fetched inside the PUT handler; `manager.send_config_update` *doesn't send anything* — it mutates a field in memory, so its name lies and the Puryfi client's own `configuration` is never actually pushed on config change.

18. **No tests whatsoever** — *(testing)*. Zero test files on either side. The bug in #2 is exactly the kind a single round-trip API test would have caught.

19. **Brittle DB-name parsing** — *(maintainability)*. `db.py` extracts the database name via `url.rsplit("/", 1)[-1].split("?")[0]` instead of an explicit env var or `pymongo.uri_parser`. Works until it doesn't.

20. **Fragile response handling** — *(robustness)*. Webhook does `data["event"]` (KeyError → naked 500 on malformed payloads); `lock_unfrozen` does `unlockResponse['type']` (KeyError if the plugin's error payload lacks that key; use `.get`); queued `enterLockPassword` can send `{"secret": None}` if the password was never set.

21. **Infra nits** — *(deployment)*: no `depends_on` with `condition: service_healthy` between `server` and `mongo` (server can crash-loop on first boot); `VITE_APP_VERSION="0.2.1"` in compose embeds literal quotes in the value; version is hardcoded in compose instead of read from `package.json`/`pyproject.toml`.

22. **Known-but-unfixed clipboard bug** — *(UX)*. `ShowPuryfiPassword` has a `#TODO` noting `navigator.clipboard.writeText` throws inside the Chaster iframe (missing `allow="clipboard-write"` permission, which is not under your control) — implement a textarea-select fallback, since this is the *emergency password* UX.

23. **Frontend hygiene** — *(maintainability)*: duplicated config type definitions in `types/chaster.ts` and `types/api.ts`; `console.log(session)` / `console.log(response.data)` left in; the `hasFetched` ref is a StrictMode band-aid (fine, but a query library or a module-level cache would be cleaner); `server/.env.example` ships a real-looking webhook password (`adkasakeWSiie2lk1o`) — rotate it if it's live anywhere.

---

## Specific recommendations

**1. Actually authenticate the webhook** (5 minutes):

```python
@router.post("/extensions/chaster")
async def chaster_webhook(request: Request, _: str = Depends(verify_credentials)):
    ...
```

While there: parse defensively (`data.get("event")`, return 400 on missing keys) and store `requestId` in a small dedup collection (or a set with TTL) to make retries no-ops.

**2. Fix the session schema so the password feature exists:**

```python
class ChasterExtensionSessionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    is_online: bool = False
    has_linked_plugin: bool = False
    link_token: str | None = None
    config: ChasterExtensionConfigSchema | None = None
    lock_password: str | None = None   # <-- the missing field
```

Then delete the bogus `lock_on_freeze=`/`unlock_on_unfreeze=` kwargs in `create_link_token`. Add one test that round-trips `fetch_session` and asserts `lock_password` survives serialization — this bug class dies permanently with that test.

**3. Fix the frontend image build** — compose needs build args, not runtime env:

```yaml
front:
  build:
    context: ./front
    args:
      VITE_BACKEND_URL: ${BACKEND_URL}
      VITE_PURYFI_WS_URL: ${WEBSOCKET_URL}
      VITE_APP_VERSION: ${APP_VERSION:-0.2.1}
```

and declare all three `ARG`s in `front/Dockerfile` before `npm run build`.

**4. Replace `requests` with `httpx.AsyncClient`.** This is the highest-leverage refactor in the backend. Create one module-level client with a timeout and the auth header, and share it:

```python
import httpx, os

chaster_client = httpx.AsyncClient(
    base_url="https://api.chaster.app",
    headers={"Authorization": f"Bearer {os.getenv('CHASTER_DEVELOPER_TOKEN', '')}"},
    timeout=10.0,
)

async def add_time_to_lock(session_id: str, duration: int) -> bool:
    try:
        r = await chaster_client.post(
            f"/api/extensions/sessions/{session_id}/action",
            json={"action": {"name": "add_time", "params": duration}},
        )
        return r.status_code == 201
    except httpx.HTTPError as e:
        logger.warning("add_time failed: %s", e)
        return False
```

(close it in the lifespan shutdown). Callers become `await add_time_to_lock(...)`.

**5. Harden the WebSocket lifecycle:**

```python
@router.websocket("/{user_link_token}")
async def websocket_endpoint(websocket: WebSocket, user_link_token: str):
    cfg = await UserLockConfiguration.find_one(
        UserLockConfiguration.link_token == user_link_token
    )
    if cfg is None:
        await websocket.close(code=4004)  # don't accept-then-hang
        return

    await websocket.accept()
    connection = Connection(websocket, cfg)
    manager.add(connection, user_link_token)
    try:
        while True:
            await connection.handle_message(await websocket.receive_bytes())
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS handler error")
    finally:
        manager.remove(user_link_token)
        connection.fail_pending("connection closed")  # resolve/cancel futures
```

and add a timeout in `send_message`: `return await asyncio.wait_for(future, timeout=15)` with a `finally: self.pending_requests.pop(response_id, None)`.

**6. Constrain `postMessage`:**

```ts
const CHASTER_ORIGIN = "https://chaster.app";
// inbound:
if (e.origin !== CHASTER_ORIGIN || typeof e.data !== "string") return;
// outbound:
window.parent.postMessage(msg, CHASTER_ORIGIN);
```

**7. Fix queue semantics:** drain sequentially (`for msg in queued: await process(...)`) instead of `create_task`; delete each message only after a successful send; start draining only after intents are granted; add a TTL index (e.g. expire after 7 days) and a per-token cap.

**8. Small correctness pass:** bind `limit_count` in `SessionSettings.tsx`; use `.get("type")` on plugin responses; allowlist `FRONT_URL` in CORS; fail fast at startup if `CHASTER_DEVELOPER_TOKEN` is empty (pydantic-settings with required fields instead of `os.getenv(..., "")` scattered across four modules — the token is currently read at import time in three different files).

---

## Bigger-picture suggestions

- **Contract drift is the systemic risk.** Issues #2 and #16 are the same bug: two hand-maintained copies of the API shape. Generate the TS types from the pydantic schemas (e.g. `datamodel-code-generator`, or a small codegen script run in CI), or at minimum add a CI step that fails when the frontend types don't match a recorded OpenAPI snapshot of the backend.
- **Get a test floor before adding features.** Priority order: (a) webhook auth + dispatch tests, (b) `fetch_session` serialization test (catches #2), (c) freeze/unfreeze handler tests with a mocked `Connection`, (d) queue drain ordering test. `pytest` + `httpx.ASGITransport` + `mongomock-motor` (or a testcontainer) covers all of it without new infra. Frontend: vitest for the two config components is enough to start.
- **Introduce a `logging` setup with redaction** and delete every `print`/`pprint`. One `logging.basicConfig` in `main.py`, then `logger = logging.getLogger(__name__)` per module. Decide explicitly what may be logged (never tokens, never `lock_password`, never full Chaster payloads).
- **Type the Puryfi wire protocol.** `handle_message` dispatches on raw dicts. Define pydantic models for each inbound/outbound message type and validate at the boundary — the `['type']` vs `.get('type')` class of bugs comes for free, and the protocol becomes self-documenting. Add a `version` field to the manifest handshake while the client base is tiny.
- **Configuration via `pydantic-settings`.** One `Settings` object, validated at startup, injected where needed — kills the duplicated `os.getenv` reads, the import-time evaluation order hazards, and gives loud failures instead of silent empty-string tokens.
- **Acknowledge the singleton's scaling ceiling.** `ConnectionManager` is in-memory, so the deployment is pinned to one uvicorn worker and one replica. That's fine for the stated scale — but write it down (a comment + a note in the README), because the day it scales out, `is_online` and message routing silently break. If that day comes: Redis pub/sub for routing + a shared connection registry, with sticky sessions as the cheap intermediate step.
- **Observability for a safety-adjacent app:** given this software literally controls a lock, add a `/healthz` (mongo ping), and consider a small audit trail collection for state-changing events (freeze → password generated → delivered/queued → unlocked). When a user says "my lock didn't unlock," there are currently stdout `print`s and nothing else.
- **Tech-debt housekeeping:** remove the unused `User` document (or build the feature that needs it), centralize the duplicated Chaster typings (`typings/chaster.py` vs. actually parsing responses — `fetch_session` declares `PartnerGetSessionAuthRepDto` and then uses raw `.get` chains instead), and add ruff + pyright to CI so the unused imports and unreachable code get flagged mechanically instead of in code reviews.

**Bottom line:** fix #1–#3 before anyone else deploys this (they're each under an hour), schedule #4–#6 as the next work session, and let the test floor + contract codegen guard everything after that. The bones are good — the gaps are in verification, not in design.
