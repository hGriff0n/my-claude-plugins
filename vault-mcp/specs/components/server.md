# Server Component

The process entrypoint. Wires up the database, parsers, and routes, and exposes the result as both a REST API (FastAPI) and an MCP server (FastMCP).

## Layout

- `src/server.py` — entrypoint. Creates the FastAPI app, registers tables, initializes parsers (which seeds the database via immediate watcher firings), and starts the watcher / write debouncer.
- `src/routes/server.py` — walks `src/routes/<system>/<op>/route.py` files and registers each handler into the FastAPI app (see `arch/routes.md` Aggregation).

## Startup sequence

1. Initialize logging per `specs/components/logging.md` (stderr + rotating file handler under `logs/`) before any other work, so subsequent steps can log failures.
2. Construct the FastAPI app.
3. Construct the database, watcher, and write debouncer (see `components/database.md`, `components/asyncfile.md`).
4. **Register tables for every system, in one pass.** For each system, import its generated `src/schemas/<name>.py` and call `database.register(...)` for the types listed in `specs/systems/<name>/readme.md`'s `tables: [...]`. All systems' tables must be registered before any parser is initialized — initialize-time watcher firings may issue cross-system queries.
5. Probe Obsidian for the active vault root (see Degraded mode below). If unavailable, **defer step 6** and start in degraded mode; otherwise continue.
6. **Initialize parsers.** For each system, instantiate its parser and call `parser.initialize(database, watcher, debouncer)`. This registers the system's debouncer config and watchers; the watchers fire immediately for current matching state, which seeds the database transitively via `parse(...)` → `database.update(...)`. There is no separate scan / seed pass.
7. Walk `src/routes/<system>/<op>/route.py` modules and register each handler.
8. Start the watcher's live event loop and the write debouncer's resolver loop.
9. Wrap the FastAPI app with `FastMCP.from_fastapi(...)` so every route is automatically exposed as an MCP tool.
10. Serve.

## Degraded mode

The server depends on Obsidian being running to discover the active vault root. If the Obsidian CLI is unavailable or no vault is configured at startup, the server still binds and serves rather than exiting:

- Logging is initialized normally so the failure is recorded.
- Tables are registered and the FastAPI app, MCP wrapper, and routes are all built — but parsers are not initialized (so the database is empty) and the watcher / write debouncer loops are not started.
- Vault-dependent endpoints respond with HTTP 503 until parser initialization completes.
- A background retry loop re-probes Obsidian on a fixed interval; once the vault becomes reachable, the deferred parser-initialization step runs (seeding the database via immediate watcher firings) and the watcher / debouncer loops start, transitioning the server out of degraded mode without a restart.
- The retry loop exits cleanly on shutdown.

## Configuration

Vault root and other deployment-time settings come from environment variables / a config file consumed by `server.py`. The database, parsers, and routes do not read environment directly; `server.py` injects what they need.

## Shutdown

On shutdown, the watcher loop is cancelled, any pending debounced writes are flushed, and the database is closed.
