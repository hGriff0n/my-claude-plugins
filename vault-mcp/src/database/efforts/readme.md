# Efforts Database

Implements `specs/arch/database.md` for the efforts system. See `specs/systems/efforts.md` for the domain model and `src/schemas/efforts.md` for the schema contract.

## `db.py`

Holds an in-memory dict of `Effort` keyed by name. The store is rebuilt by `vault/efforts/parser.scan`.

### Reads

- `list(status: EffortStatus | None = None) -> list[Effort]` — all efforts, optionally filtered.
- `get(name: str) -> Effort | None`

### Mutations

Each mutation persists via `vault/efforts/parser` (which uses `obsidian_cli`) and then re-syncs the affected index entry.

- `init(vault_root: Path)` — calls `parser.scan(vault_root)` and populates the store. Called once at startup.
- `create(name: str) -> Effort` — fails if `get(name)` is non-null. Calls `parser.create(name)`, then re-scans and returns the new entry.
- `move(name: str, *, backlog: bool = False, archive: bool = False) -> Effort | None` — validates the requested transition against the current status, calls `parser.move(name, backlog=…, archive=…)`, then re-scans. Returns the updated `Effort`, or `None` if the effort was archived (drops from the index).
- `refresh()` — re-runs `parser.scan` to rebuild the entire index. Triggered by `vault/debounce` on external changes under `efforts/`.

### Transition rules

`move` enforces:
- `backlog=True` requires current status `ACTIVE`.
- `archive=True` is allowed from any status.
- `backlog=False, archive=False` (re-activate) requires current status `BACKLOG`.

Invalid transitions raise `ValueError`; the route layer maps these to HTTP 400.
