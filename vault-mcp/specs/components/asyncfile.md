# AsyncFile Component

Owns the asynchronous boundary between vault files and the database. Two independent mechanisms live here:

- **Parse coalescer** — inbound. External file events → coalesced parser callbacks.
- **Write debouncer** — outbound. Database edits → coalesced file writes after a per-system quiet window.

These are *not* the same debounce. Different inputs, different coalescing keys, different windows. Sections below treat them independently.

## Layout

- `src/vault/watcher.py` — file event source, watcher registry, parse coalescer.
- `src/vault/debounce.py` — write debouncer; resolves DB-first edits back to disk.

Both are domain-free utilities. They expose primitives (register / enqueue / dispatch) and do not import from any system parser. Per-system orchestration (which watchers to register, what lag to use) lives in the parser (see `arch/parser.md`).

## Watcher

### Watch criteria

A **watch criterion** is `(target: Path, events: set[EventType])` where `events ⊆ {create, modify, delete}` and `target` is *always* a specific file or folder. There is no prefix-path matching at this layer — every watch names exactly one path.

A folder target matches events on the folder itself (e.g. a new file created directly inside it, or the folder being moved/deleted), not events on arbitrarily nested descendants. Parsers that need to react to descendants register their own targeted watchers as they discover them.

> What looks like a "global" watch is just a single watcher on a well-known root file or folder. The tasks system, for example, registers one watcher on its single global taskfile; per-task watchers for the rest of the vault are registered by the efforts parser when it parses an effort and encounters task files.

### Watcher handle

`register(...)` returns a `WatcherHandle` — an opaque token used to:

- Deregister the watcher (`watcher.deregister(handle)`).
- Stamp the **origin** of any DB write triggered by that watcher's callback, so the write debouncer can suppress backport (see *Origin propagation*).

### Surface

`src/vault/watcher.py` exposes:

- **`register(criterion, callback) -> WatcherHandle`** — registers a watcher. `callback(file: Path, event: EventType, handle: WatcherHandle) -> None` runs when a matching event fires.

  **Immediate fire on register**: before `register` returns, the watcher synchronously invokes the callback once for every existing path that currently matches the criterion (each as a `create`-equivalent event). The active origin during these synchronous invocations is the new handle, so any DB writes made by the callback are correctly attributed and not enqueued for backport. If a callback registers further watchers, those registrations also fire immediately for matching state, recursively. This is the mechanism by which a parser's `initialize` seeds the database — there is no separate scan pass.

  Idempotent on identical (criterion, callback) pairs (no duplicate immediate-fires either).
- **`deregister(handle) -> None`** — removes the watcher.
- **`retarget(handle, new_target: Path) -> None`** — convenience for renames; preserves handle identity so origin tracking continues to work across the move.
- **`start() / stop()`** — runs the underlying file event loop.

### Parse coalescer

The watcher does not invoke callbacks synchronously on every raw file event. Events are bucketed by `(handle, file)` and held for a short coalesce window (millisecond-scale, single global value). The callback fires once per bucket once the bucket goes quiet. This protects against editor save-storms (Obsidian writes multiple events per save).

The coalesce window is independent of the write debouncer's lag and is not configurable per system.

### Origin propagation

While a watcher callback is running, the watcher exposes the firing handle as the **active origin** for that call frame. Callers performing DB writes inside the callback pass that handle through to the database (the database surface and exact propagation rules are defined in `components/database.md`). The write debouncer reads the origin to decide whether to enqueue a backport.

Two cases:

- **Origin set** (callback path) → file is already authoritative, no backport.
- **Origin unset** (route handlers, scripts) → backport is enqueued.

### Self-write registry

When the write debouncer flushes a file, the resulting file event must not echo back as an external change. The watcher consults a self-write registry the debouncer maintains, suppressing the next event for that path within a short window after a backport write. Writes performed by parsers via Obsidian or direct I/O for non-debounced systems also register here.

## Write debouncer

### Surface

`src/vault/debounce.py` exposes:

- **`enqueue(file: Path, lag: timedelta) -> None`** — registers that `file` needs to be re-projected from the database after at least `lag` of disk quiescence. Multiple enqueues for the same file coalesce; the maximum lag wins.
- **`flush(file: Path | None = None) -> None`** — forces immediate backport of `file` (or all pending). Used at shutdown.
- **`start() / stop()`** — runs the periodic resolver loop.

The debouncer is consumed by the database, not parsers directly.

### Lag and coalescing

- **Lag is per-system** and chosen at the parser layer (see `arch/parser.md`). Some systems set `lag = 0` (write-through, no debounce — efforts).
- **Quiescence**: an entry only fires if no external watcher event has touched the file within the lag window. This prevents the debouncer from clobbering a file the user just edited in Obsidian.
- **Coalescing key** is the *parent file path*, not the element id. A single effort file may receive many DB updates (frontmatter + several tasks) and is rewritten once.
- The resolver loop scans the pending set on a single global cadence; per-file lag controls when each entry is *eligible*, not when the loop runs.

### Backport flow

When a pending entry is eligible:

1. The debouncer asks the owning parser (registered with the debouncer at parser-`initialize` time — see `arch/parser.md`) to project the file from the current database state.
2. The parser builds the file content and persists it.
3. The path is registered with the self-write registry so the resulting file event is suppressed at the watcher.
4. **Only after** the writer call returns successfully is the WAL cleared for that file. A failed projection leaves the WAL intact so the next tick (or the next process start) retries.

The DB is the source of truth at backport time — the parser does not re-read the file before writing.

### Pending writes and the WAL

The debouncer maintains two pieces of state per file with outstanding edits:

- **`_pending`** — in-memory dirty markers (one entry per file, just `(file, system, eligible_at)`). Drives the resolver loop. Lost on crash.
- **WAL** — append-and-compact log of per-element mutations (`system`, `model`, `identity`, `deleted`, `file`, `payload`). Survives crashes.

WAL entries are keyed by `(system, model, identity)`. When `wal_record` is called for an element that already has an outstanding entry, the existing line is **replaced in place** rather than appended. This keeps the WAL bounded (one entry per pending element) and matches "latest write wins." The compaction is part of the record operation, not a separate maintenance pass.

On startup, `wal_replay` reads each entry and, for each one, compares the WAL payload against the element currently in the DB:

- **DB matches WAL** → skip; the mutation already reached the DB before the crash. No re-enqueue.
- **DB differs or element absent** → call `db.update(elem, origin=None)` / `db.delete(elem, origin=None)`. The `origin=None` re-enters the normal write path and repopulates `_pending`, so the next resolver tick projects the file.

Successful projection clears every WAL entry for that file (step 4 above).

### Inbound reconciliation against pending writes

Pending writes represent DB state that has not yet been written to disk. When the watcher fires for a file with outstanding pending writes, the parsed file may legitimately disagree with the DB about elements that are mid-projection. Without reconciliation, the watcher would create a duplicate row whenever it parses an element that the DB already has a pending update for under a different identity (e.g. a task the user typed without an ID, which the DB has since assigned an ID to).

The debouncer exposes a query:

- **`pending_elements(file: Path) -> list[(model, payload)]`** — returns the current WAL entries for `file`, deserialized to their pydantic models. Order is insertion order.

Parsers consult this during their watcher callback **before** issuing a `db.update` for an element they cannot match by identity. The matching rule (which fields constitute "the same element when identity is missing") is parser-specific and lives in the parser spec, not here. If the parser finds a match, it issues the `db.update` using the pending element's identity rather than creating a new one. If it finds no match — or the match is ambiguous — it falls through to the normal create path.

The mechanism itself is content-agnostic. The debouncer exposes pending elements; the parser decides what counts as a match.

## Open questions

- **Folder-move ordering.** When a user moves an effort folder inside Obsidian, both the effort-level watcher and any per-task watchers under it may fire. Order is non-deterministic across OSes, and the work performed differs depending on which fires first (effort first → tasks re-resolve against the new path; tasks first → tasks emit updates referencing a path the effort hasn't yet relocated). Resolution TBD.
- **Ambiguous reconciliation matches.** If a parser finds multiple pending elements that plausibly match an unidentified parsed element, current behavior is "fall through to create." This may produce duplicates the user has to clean up. Whether to instead block the write and surface an alert is TBD.
