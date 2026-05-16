# Parser Spec Template

Defines the contract every `src/vault/<system>/parser.py` module must follow. The vault layer owns the on-disk representation of each system; system specs (e.g. `specs/systems/efforts/readme.md`) describe how their parser implements this contract.

## Files

Each vault system is a folder under `src/vault/<name>/` with these required files:

| File | Purpose |
|---|---|
| `parser.py` | Implements the three-method surface defined below. "Parser" is a logical name — it may parse files (tasks) or walk a directory tree (efforts). |
| `test.py` | Unit tests for the parser. |

The system's spec (Initialize / Parse / Write Operations sections) lives under `specs/systems/<name>/readme.md`; there is no per-parser readme.

## Lifecycle

A parser has a single setup hook, called once at server startup:

- **`initialize(db, watcher) -> None`** — the parser uses this call to register its initial watchers. Each registration *immediately invokes* the callback for every existing file/folder that matches the criterion (treated as create-equivalent events) before `register` returns. Those callback invocations call `parse(...)`, which populates the database and may register further watchers — those further registrations also fire immediately for matching state. The recursion terminates naturally once no new watchers are produced. See `components/asyncfile.md`.

The parser assumes that table registration is performed externally by the server before `initialize` is called (see `components/server.md`). When `initialize` returns, the database has been fully seeded for that system. There is no separate seed pass.

A parser that needs to project DB state back to disk registers each writable target with `EventType.FLUSH` included in its watch criteria. Callbacks then dispatch on event type: CREATE/MODIFY/DELETE drive parsing; FLUSH drives projection.

## Surface

A parser exposes exactly three methods:

- **`parse(file: Path) -> List[ItemType]`** — converts a single file or folder into one or more schema instances. The parser is responsible for recursing into folders if the unit is a directory, and for populating the schema types defined in `specs/systems/<name>/schema.yaml`. `parse` may register additional watchers as it discovers new files/folders that need monitoring (e.g. effort `parse` registers a per-task-file watcher for each task file it finds inside the effort directory). Re-parsing an already-known unit reuses existing watcher handles where possible; the parser tracks which handles it has registered for which targets, and uses `watcher.deregister` / `watcher.retarget` when an `update` causes a target to disappear or move.
- **`update(elem: ItemType, op: UpdateTypes) -> None`** — applies a write operation to a single schema instance. `UpdateTypes` is a system-specific type (typically a tagged union) enumerating the supported mutations; each system defines its own in its `### Write Operations` section. `update` mutates the database and, when the call originates outside a watcher callback, marks the owning file dirty via `watcher.mark_dirty(file)` so a FLUSH eventually projects the change to disk. When the call originates from a watcher callback the active origin is set and no dirty mark is issued (the file is already authoritative). `update` performs no synchronous file I/O.

The third method is the **flush callback**, dispatched by the watcher when a dirty target has gone quiet. By convention this is a private method on the parser (e.g. `_on_flush`) bound at registration time; it does not appear on the protocol because its signature is the standard watcher callback. The flush callback:

1. Reads the current on-disk content (the source of truth for any user edits made during the inactivity window).
2. Field-merges the parsed state against the database state (per-system rule — the system spec defines which fields the parser-side updates own and which the file owns).
3. Writes the merged result, then calls `watcher.mark_self_write(file)` so the resulting MODIFY does not echo back.

`parser.py` imports schema types from `src/schemas/<name>.py`. It does **not** import from the database (no upward dependency).

### Interface

`src/vault/parser.py` defines a generic python protocol (https://typing.python.org/en/latest/spec/protocol.html) with the above interface surface. It takes two generic parameters, `ItemType` (defining the schema type the parser is interacting with) and `UpdateTypes` (a union/enum of the allowable write operations). Type annotations should use this object with the requisite generic parameters where needed. Each system parser file should also export a typedef for the protocol with the generic parameters filled in.

## Write backends

Each flush call lands on disk through one of two backends, chosen per call by the parser:

- **Through Obsidian** — invoke `vault/obsidian_cli.py` for writes that need Obsidian's index to see them immediately (e.g. creating notes from templates).
- **Direct file I/O** — for high-frequency or batched updates (e.g. task field edits).

Both backends register the resulting file event with the watcher's self-write registry (see `components/asyncfile.md`) so the change does not echo back as an external event.

## Shared vault modules

- `vault/watcher.py` — the asyncfile component. See `components/asyncfile.md` for the full surface (watcher registration with immediate-fire semantics, parse coalescing, dirty/flush dispatch, self-write registry).

## Variants

A system whose on-disk representation isn't a single file (efforts → directory layout) still implements the same surface. Only the internals of `parse` / `update` / `_on_flush` differ. The arch contract is the surface, not the implementation strategy.
