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

- **`update(elem: T, origin: WatcherHandle | None) -> None`**
  - Upserts `elem` keyed by the existing identity of `elem`. Replaces the row.
  - `origin` identifies the watcher whose callback is currently driving this write, or `None` for DB-first edits originating outside a watcher (route handlers, scripts, parser-internal logic).
  - After the upsert, the database consults the write debouncer (see `components/asyncfile.md`):
    - `origin is None` → resolve `elem`'s parent file via the owning system's `parent_file_resolver` (registered with the debouncer at `parser.initialize` time) and `debouncer.enqueue(parent_file, lag)` with that system's configured lag.
    - `origin is not None` → skip enqueueing; the file is already authoritative for this change.
  - Callers that are inside a watcher callback are responsible for passing the active `WatcherHandle` through to `update`. The active origin is exposed by the watcher dispatch layer; the database does not infer it from call-stack state.

## Field flattening

When `register` is called, nested pydantic structs are flattened into dotted column names (e.g. `time_details.created`, `display.task_stats.num_by_status`). Lists and dict-typed fields are stored as JSON columns. Enums are stored as their string values.

## Initialization

At server startup, table registration happens in a single pass across **all** systems before any parser is initialized — for every system, the server imports the generated `src/schemas/<name>.py` and calls `register(...)` for each type listed under that system's readme `tables: [...]`. Only once every system's tables exist does the server begin invoking `parser.initialize(db, watcher, debouncer)` per system; this ordering matters because a parser's initialize-time watcher firings may issue cross-system queries that depend on other systems' tables already being present.

Seeding falls out of `parser.initialize`: the watchers it registers fire immediately on existing files and populate the database via `parse(...)` → `update(...)` (see `arch/parser.md` and `components/asyncfile.md`). After startup, live watcher events drive subsequent `update(...)` calls.

## Cross-system access

Any registered table is queryable by any caller. Cross-system reads are simply queries against another table; there is no special channel. Cross-system *writes* go through the owning system's documented write operations (its parser `write` and the routes that wrap it) — do not `update(...)` another system's table directly outside that system's code.

This implies that there is an interface to get the tables for a given system

## System-specific wrappers

A system may add convenience wrappers (e.g. `tasks_by_effort(effort_name)`) inside its own module. These are thin compositions of `query(...)` and live with the system, not in the database component. The component itself stays generic.

<!-- Rework to move query/writing onto a table object. the database now merely works as table registration/resolution plus provides the actual query runners that the tables use. users call getTableForSystem or some sort and then run the sql query through the returned table object -->