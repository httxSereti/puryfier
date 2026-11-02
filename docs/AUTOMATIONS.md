# Automations — technical reference

> Event-driven automation engine for Puryfier.
> MongoDB is the source of truth. The Chaster extension configuration keeps a best-effort snapshot.

---

## 1. Overview

```text
Event → matching automations → conditions → actions → execution audit
```

An automation belongs to **one Chaster session**. It can be duplicated into another lock, but the copy is independent and starts disabled.

---

## 2. MongoDB collections

### `automations`

| Field | Description |
| --- | --- |
| `session_id` | The lock this automation belongs to |
| `lock_id`, `lock_label` | Display metadata |
| `owner_id` | Chaster user id of the creator |
| `owner_role` | `keyholder` or `wearer` |
| `name` | Display name |
| `status` | `active` or `archived` |
| `enabled` | Runtime switch |
| `priority` | Execution order |
| `trigger` | Event + conditions + occurrence settings |
| `actions` | Ordered action list |
| `limits` | Cooldown and optional daily cap |
| `source_automation_id` | Set on a duplicated rule |
| `disabled_by`, `disabled_by_role` | Audit of who disabled it |
| `archived_at` | TTL index: 30 days |

### `media_counters`

One document per `(session_id, automation_id)`:

```json
{
  "session_id": "...",
  "automation_id": "...",
  "occurrence_count": 2,
  "window_started_at": "...",
  "last_triggered_at": null,
  "updated_at": "..."
}
```

Counters are updated in memory on the WebSocket hot path and flushed in batches every 15 seconds. Threshold crossings are persisted immediately.

### `automation_executions`

Audit trail with a 90-day TTL:

```json
{
  "session_id": "...",
  "automation_id": "...",
  "automation_name": "Eyes and Belly",
  "event_id": "...",
  "event_type": "puryfi.media.scan",
  "status": "success",
  "actions": [{ "type": "chaster.add_time", "status": "success" }],
  "error": null,
  "started_at": "...",
  "finished_at": "..."
}
```

---

## 3. Rule schema

```json
{
  "name": "Eyes and Belly",
  "enabled": true,
  "priority": 100,
  "trigger": {
    "event": "puryfi.media.scan",
    "conditions": [
      { "field": "labels", "op": "contains_all", "value": ["Eye", "Tummy"] }
    ],
    "min_score": 0.5,
    "count": 3,
    "window_seconds": 300,
    "count_mode": "images"
  },
  "actions": [
    { "type": "chaster.add_time", "params": { "seconds": 120 }, "on_failure": "stop" }
  ],
  "limits": {
    "cooldown_seconds": 300,
    "max_per_day": 20
  }
}
```

### Supported events

- `chaster.session.joined` (Chaster `extension_session.created`)
- `chaster.session.left` (Chaster `extension_session.deleted`)
- `chaster.lock.frozen`
- `chaster.lock.unfrozen`
- `puryfi.media.scan`
- `puryfi.connection.ready` (PuryFi `ready` accepted)
- `puryfi.connection.disconnected` (PuryFi socket closed)
- `puryfi.enabled` (PuryFi `stateChange` on `enabled` becoming `true`)
- `puryfi.disabled` (PuryFi `stateChange` on `enabled` becoming `false`)
- `puryfi.locked` (PuryFi `stateChange` with a `lockConfiguration`)
- `puryfi.unlocked` (PuryFi `stateChange` without a `lockConfiguration`)

The last known `enabled` / lock state is persisted with the lock session. When
PuryFi reconnects, the initial `getState` snapshot is compared with that saved
value, so a transition that happened while the socket was down still emits the
corresponding event.

A successful `requestPluginIntents` response is treated as the grant itself:
some PuryFi runtimes authorise the requested intents without sending an
`intentsGrant` echo. Puryfier therefore does not block the protected setup while
waiting for one. If the runtime keeps the intents pending, Puryfier re-sends the
plugin manifest with a temporary description to force the storage update that
triggers PuryFi's own intent-grant handler, then restores the manifest.

### Supported conditions

| Field | Operators |
| --- | --- |
| `labels` | `contains_all`, `contains_any`, `not_contains`, `eq`, `neq` |
| `score` | `gte`, `lte`, `eq`, `neq` |
| `object_count` | `gte`, `lte`, `eq`, `neq` |
| `chaster_frozen` | `eq`, `neq` |
| `puryfi_enabled` | `eq`, `neq` |
| `puryfi_has_lock` | `eq`, `neq` |

### PuryFi protocol events

PuryFi events are emitted from the live WebSocket connection and evaluated by the
same engine as Chaster events. Their context is a snapshot of the connection:

| Field | Meaning |
| --- | --- |
| `chaster_frozen` | Last freeze state persisted from a Chaster webhook |
| `puryfi_enabled` | Last `enabled` state reported by PuryFi (`null` if unknown) |
| `puryfi_has_lock` | Whether PuryFi currently reports a lock configuration |

When a lock-control intent is revoked, a server warning is written and
protected commands stay in the durable queue until the permissions return.

The configuration editor exposes ready-made templates for the common guard
behaviours: reapply the lock on reconnect, warn on a disconnect while frozen,
and warn when PuryFi is disabled while frozen. The PuryFi profile itself is
always updated automatically, but account changes do not emit automation
events.

In the extension UI, the **Automations** tab is split into **My automations**
and **Templates**. My automations can be searched, filtered by status, owner
and trigger source, and sorted by last update, creation date or name. Templates
are grouped into synchronization, media/punishment and alert categories, and
carry `puryfi` / `chaster` tags that can be combined with a text search.

### Label artwork

The configuration editor uses PuryFi's body-part artwork from
`front/public/puryfi-labels/` so labels are visual rather than only textual.

### Supported actions

| Type | Params |
| --- | --- |
| `puryfi.lock` | optional `timer_seconds`, `timer_plus` (reuses the stored password) |
| `puryfi.enable` | — |
| `puryfi.unlock` | — |
| `puryfi.disable` | — |
| `puryfi.set_lock` | `password`, optional timer fields |
| `puryfi.enter_emergency_token` | `token` |
| `chaster.add_time` | `seconds` |
| `chaster.remove_time` | `seconds` |
| `chaster.freeze` | — |
| `chaster.unfreeze` | — |
| `chaster.toggle_freeze` | — |
| `chaster.pillory` | `duration` (seconds), optional `reason` |
| `chaster.set_timer_visibility` | `display_remaining_time` (boolean) |
| `chaster.log` | `title`, `description` |

`chaster.freeze`, `chaster.unfreeze`, `chaster.toggle_freeze`, `chaster.pillory`
and `chaster.set_timer_visibility` call Chaster's extension lock actions. They
are useful for punishing a PuryFi disconnect, rolling a freeze with
`toggle_freeze`, pillorying censored media, or hiding the remaining time while
the lock is frozen.

---

## 4. Occurrence semantics

For `puryfi.media.scan`:

- media rules have a default `min_score` of **0.5**; lower-confidence detections are ignored;
- each image that satisfies the conditions increments the counter once (`count_mode: "images"`);
- `count_mode: "objects"` counts matching detections instead;
- `count` is the threshold;
- `window_seconds = 0` means the counter never expires;
- after a trigger, the counter resets;
- media automations always have a minimum cooldown of 5 seconds;
- a failed `chaster.add_time` restores the consumed count so it can be retried;
- `max_per_day` is an in-memory safety guard and resets when the process restarts.

Example: `count = 3`, `window_seconds = 300` means “3 matching images within 5 minutes”.

---

## 5. Permissions

| Action | Keyholder | Wearer |
| --- | --- | --- |
| View rules | Yes | Yes |
| Create/edit/delete own rules | Yes | If `wearer_can_manage` |
| Edit/delete another creator's rule | No | No |
| Disable any rule on the lock | Yes | No |
| Re-enable a rule disabled by the keyholder | Yes | No |
| Duplicate own rule | Yes | If `wearer_can_manage` |

`wearer_can_manage` is stored per lock in the Chaster configuration and mirrored in MongoDB. It defaults to false when a keyholder exists, and to true for self-locks.

The separate `wearer_can_control` permission (stored in `puryfi_permissions`) controls whether the
wearer may operate Puryfi (enable, disable, lock or unlock). `null` means the creator did not
choose: it resolves to true for self-locks and false when a keyholder exists. An explicit choice
always wins. Once the session exists, a wearer can never change it, and a self-lock freezes its
choice for the whole lock.

---

## 6. Duplication and archive

- Duplication is explicit: `POST .../automations/{id}/duplicate`.
- The source must belong to the caller.
- The target must be a lock where the caller has the same role.
- The copy starts **disabled** and gets a new id.
- It is independent: editing the copy does not edit the source.
- When a lock ends, its rules become `archived`, `enabled = false`, and are kept for 30 days.
- Archived rules can be duplicated into a new lock; their counters and history are not copied.

---

## 7. API

| Method | Path |
| --- | --- |
| GET | `/api/configuration/{token}/automations` |
| GET | `/api/configuration/{token}/automations/catalog` |
| POST | `/api/configuration/{token}/automations` |
| PATCH | `/api/configuration/{token}/automations/{id}` |
| DELETE | `/api/configuration/{token}/automations/{id}` |
| POST | `/api/configuration/{token}/automations/{id}/duplicate` |
| POST | `/api/configuration/{token}/automations/migrate` |
| GET | `/api/session/{main_token}/automations` |
| GET | `/api/session/{main_token}/automations/catalog` |
| POST | `/api/session/{main_token}/automations` |
| PATCH | `/api/session/{main_token}/automations/{id}` |
| DELETE | `/api/session/{main_token}/automations/{id}` |
| POST | `/api/session/{main_token}/automations/{id}/duplicate` |
| PUT | `/api/session/{main_token}/permissions` |

---

## 8. Performance

The media hot path is synchronous and I/O-free:

1. extract labels once;
2. build a label bitmask;
3. skip rules whose required labels are absent;
4. update in-memory counters;
5. create a supervised trigger task only when a threshold is crossed.

No MongoDB or Chaster call happens per scan. Counters are flushed in batches every 15 seconds. Chaster `add_time` calls are serialized per session with a 1-second gap so several matching rules cannot burst the API.

A synthetic benchmark with 100 rules and 5 labels per scan measured roughly 7.6 µs per scan for the in-memory matching step. The real bottlenecks are the network and the Chaster API, not rule evaluation.

---

## 9. Legacy migration

Legacy settings remain supported until the lock is converted:

- `lock_on_freeze` → “Lock PuryFi on freeze” (the legacy migration preserves the old score behaviour with `min_score: 0`)
- `unlock_on_unfreeze` → “Unlock PuryFi on unfreeze”
- `censorPicsConfig` → “Add time for censored media”

Conversion is explicit (`POST .../automations/migrate`). Once converted, `automation_mode = true` and the legacy code path is disabled for that session.
