# Database Component

A single, system-agnostic database component. Every system registers its schema-derived tables here; there is no per-system database module.

## Surface

The database exposes a small generic interface — no specialized per-system query helpers live in this module:

- **`register(model: type[BaseModel]) -> TableRef`**
  - Creates a table for the given pydantic model, flattening the struct so each field maps to one column.
  - Returns a `TableRef` (table name + typed handle) used by callers as the target for queries and updates.
  - Idempotent: registering the same model twice returns the same `TableRef`.

- **`query(sql: str) -> list[T]`**
  - Runs a raw SQL query against the registered tables. Results are deserialized back into the registered pydantic types.
  - Callers compose whatever SQL they need; the database does not curate per-system query helpers.

- **`update(key: T, elem: T) -> None`**
  - Upserts `elem` keyed by the existing identity of `key`. Replaces the row.

## Field flattening

When `register` is called, nested pydantic structs are flattened into dotted column names (e.g. `time_details.created`, `display.task_stats.num_by_status`). Lists and dict-typed fields are stored as JSON columns. Enums are stored as their string values.

## Initialization

At server startup, each system imports its generated `src/schemas/<name>.py`, calls `register(...)` for each type listed under its readme's `tables: [...]`, and seeds rows by running `parser.scan()` → `parser.parse(...)`. After startup, file-watcher events from `vault/debounce.py` trigger re-parses of changed files and `update(...)` calls into the database.

## Cross-system access

Any registered table is queryable by any caller. Cross-system reads are simply queries against another table; there is no special channel. Cross-system *writes* go through the owning system's documented write operations (its parser `write` and the routes that wrap it) — do not `update(...)` another system's table directly outside that system's code.

## System-specific wrappers

A system may add convenience wrappers (e.g. `tasks_by_effort(effort_name)`) inside its own module. These are thin compositions of `query(...)` and live with the system, not in the database component. The component itself stays generic.
