# AsyncFile Component

Owns the asynchronous boundary between vault files and the database. A single mechanism — the **watcher** — drives both inbound parsing and outbound flushing:

- **Parse coalescer** — inbound. External file events → coalesced parser callbacks.
- **Dirty-file flush** — outbound. Files marked dirty by parser `update()` calls → coalesced FLUSH callbacks once the file has gone quiet.

Both channels share the same poll loop and the same per-handle bookkeeping; the parser sees them as different event types arriving on the same callback.

## Layout

- `src/vault/watcher.py` — file event source, watcher registry, parse coalescer, dirty-file flush.

The watcher is a domain-free utility. It exposes primitives (register / mark_dirty / dispatch) and does not import from any system parser. Per-system orchestration (which watchers to register, what inactivity window to use, how to flush) lives in the parser (see `arch/parser.md`).

## Watch criteria

A **watch criterion** is `(target: Path, events: set[EventType])` where `events ⊆ {create, modify, delete, flush}` and `target` is *always* a specific file or folder. There is no prefix-path matching at this layer — every watch names exactly one path.

A folder target matches events on the folder itself (e.g. a new file created directly inside it, or the folder being moved/deleted), not events on arbitrarily nested descendants. Parsers that need to react to descendants register their own targeted watchers as they discover them.

> What looks like a "global" watch is just a single watcher on a well-known root file or folder. The tasks system, for example, registers one watcher on its single global taskfile; per-task watchers for the rest of the vault are registered by the efforts parser when it parses an effort and encounters task files.

`flush` is the outbound channel: a watcher that includes `flush` in its events can be marked dirty via `mark_dirty(target)` and will receive a FLUSH callback once the target has been inactive for the parser's configured inactivity window.

## Watcher handle

`register(...)` returns a `WatcherHandle` — an opaque token used to:

- Deregister the watcher (`watcher.deregister(handle)`).
- Retarget the watcher across a rename (`watcher.retarget(handle, new_target)`).
- Mark the watcher's target dirty so a FLUSH fires when it goes inactive (`watcher.mark_dirty(target)`).
- Stamp the **origin** of any DB write triggered by that watcher's callback (see *Origin propagation*).

## Surface

`src/vault/watcher.py` exposes:

- **`register(criterion, callback) -> WatcherHandle`** — registers a watcher. `callback(file: Path, event: EventType, handle: WatcherHandle) -> None` runs when a matching event fires.

  **Immediate fire on register**: before `register` returns, the watcher synchronously invokes the callback once for every existing path that currently matches the criterion (each as a `create`-equivalent event). The active origin during these synchronous invocations is the new handle, so any DB writes made by the callback are correctly attributed and do not re-mark the file dirty. If a callback registers further watchers, those registrations also fire immediately for matching state, recursively. This is the mechanism by which a parser's `initialize` seeds the database — there is no separate scan pass.

  Idempotent on identical (criterion, callback) pairs (no duplicate immediate-fires either).
- **`deregister(handle) -> None`** — removes the watcher and drops any dirty marker on its target.
- **`retarget(handle, new_target: Path) -> None`** — convenience for renames; preserves handle identity (so origin tracking and any dirty marker continue to apply across the move).
- **`mark_dirty(target: Path) -> None`** — flags `target` as having pending DB-side changes that need writing back. The watcher will fire a FLUSH callback for the registered handle whose target equals `target`, once the file has had no external MODIFY events within the parser-configured inactivity window. Idempotent; clears automatically after a successful FLUSH dispatch.
- **`mark_self_write(path: Path) -> None`** — suppress the next external event for `path` (used by parsers after they write to disk so the resulting MODIFY does not echo back).
- **`start() / stop()`** — runs the underlying poll loop.

## Parse coalescer

The watcher does not invoke callbacks synchronously on every raw file event. Inbound events are bucketed by `(handle, file)` and held for a short coalesce window (millisecond-scale, single global value). The callback fires once per bucket once the bucket goes quiet. This protects against editor save-storms (Obsidian writes multiple events per save).

## Dirty-file flush

A separate per-handle bookkeeping channel:

- `mark_dirty(target)` records the time of the call and the handle owning `target`.
- Each poll tick, the watcher inspects every dirty target. A dirty target is **eligible** when its last observed external MODIFY (or its dirty-marking time, whichever is later) is older than the parser-configured **inactivity window**.
- Eligible targets are dispatched with `EventType.FLUSH`. The active origin during dispatch is the firing handle, so any DB writes the parser performs while rebuilding the file are correctly attributed.
- On successful return from the callback the dirty marker is cleared. If the callback raises, the marker is retained and the next tick retries.

The inactivity window is a parser-level parameter, configured at watcher registration time (see `arch/parser.md`). Some systems may register with `inactivity_window = 0` (write-through, dispatch on the first eligible tick).

The parse coalescer's debounce window and the flush inactivity window are independent and are not configurable globally.

## Origin propagation

While a watcher callback is running, the watcher exposes the firing handle as the **active origin** for that call frame. Callers performing DB writes inside the callback pass that handle through to the database (the database surface and exact propagation rules are defined in `components/database.md`). The active origin is what tells the rest of the system "this DB write is reflecting state already on disk, do not re-mark the file dirty."

Two cases:

- **Origin set** (inbound parse callback or flush callback) → the file is already authoritative for the write, no dirty marker.
- **Origin unset** (route handlers, scripts) → `update()` marks the file dirty so a FLUSH eventually projects the DB state back to disk.

## Self-write registry

When a parser flushes a file, the resulting file event must not echo back as an external change. The watcher consults a self-write registry, suppressing the next event for that path within a short window after a self-write. The parser calls `mark_self_write(path)` after every disk write it performs.

## Folder moves

When an effort folder is moved inside Obsidian, both the effort-level watcher and any per-task watchers under it fire. To avoid an ordering-dependent re-parse cascade:

1. The effort parser detects the move by observing a folder rename (or create-at-new-path / delete-at-old-path pair).
2. Before letting the move land, the effort parser calls the task parser's flush helper for every dirty taskfile under the old folder.
3. The effort parser then calls `watcher.retarget(handle, new_path)` on every watcher whose target was under the old folder — including its own effort-level handle and each task-file handle.

Retargeting preserves handle identity so origin tracking, dirty markers, and self-write entries survive the move. No re-parse is triggered; the database rows are simply rewired to the new path.
