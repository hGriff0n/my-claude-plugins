# Database System Spec Template

Defines the contract every `src/database/<system>/` module must follow. Implementation specs (e.g. `src/database/efforts/readme.md`) MUST reference this template.

## Files

Each database system is a folder under `src/database/<name>/` with these required files:

| File | Purpose |
|---|---|
| `db.py` | In-memory store + read/write interface. Holds the live schema instances. |
| `readme.md` | System spec — references this template, describes the db surface. |
| `test.py` | Unit tests for db. |

The system's domain types are **not** defined here. They live in `src/schemas/<system>.py` as pydantic models and are imported by `db.py`. See `arch/schemas.md`.

## Schema (external)

- Domain types live in `src/schemas/<system>.py` as pydantic models — the canonical shape used by both `db` and route responses.
- State-modification methods (e.g. `task.add_blocker(id)`) live on the pydantic model in `schemas/`, since pydantic v2 supports methods on models. No I/O on these methods.
- `db` imports types from `schemas/`; it does not redefine them.

## `db.py`

The single source of truth for the system's in-memory state. **Every mutation to a system's data — whether triggered by a route, a watcher event, or initial scan — passes through `db`.**

Required surface:

- **Initialization** — `init(vault_root)` populates the in-memory store by calling `vault/<system>/parser.scan(...)`. Called once at server startup.
- **Reads** — query helpers that return schema instances (e.g. `list(...)`, `get(id)`).
- **Mutations** — `create(...)`, `update(id, ...)`, `move(...)`, etc. Each is the single entry point for a kind of change. Internally, a mutation coordinates updating the in-memory schema and calling `vault/<system>/parser` to persist on-disk state. The order and split (in-memory-first vs. parser-then-rescan) is a per-system choice; the contract is that after the call returns, both layers are consistent.
- **Refresh** — `refresh(...)` rebuilds the in-memory store from the vault. Called by `vault/debounce` on external file changes (writes that did not originate from `db`).

## Self-write convention

When a mutation persists via direct file I/O, `db` registers the write with `vault/debounce` so the watcher does not fire `refresh()` for changes that originated here. Writes that go through `obsidian_cli` (Obsidian-mediated) do not need this — the resulting watcher event triggers a `refresh()` that is idempotent.

## Cross-system access

`db.<system>` may import another `db.<other_system>` for read-only access (e.g. tasks reading effort names). Cross-system mutations must go through the owning system's `db` — never reach into another system's schema directly.
