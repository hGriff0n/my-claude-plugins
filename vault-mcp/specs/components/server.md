# Server Component

The process entrypoint. Wires up the database, parsers, and routes, and exposes the result as both a REST API (FastAPI) and an MCP server (FastMCP).

## Layout

- `src/server.py` — entrypoint. Creates the FastAPI app, registers tables, runs initial scans, and starts the watcher.
- `src/routes/server.py` — walks `src/routes/<system>/<op>/route.py` files and registers each handler into the FastAPI app (see `arch/routes.md` Aggregation).

## Startup sequence

1. Initialize logging per `specs/components/logging.md` (stderr + rotating file handler under `logs/`) before any other work, so subsequent steps can log failures.
2. Construct the FastAPI app.
3. Probe Obsidian for the active vault root (see Degraded mode below). If unavailable, skip steps 4–5 and start in degraded mode; otherwise continue.
4. For each system, import its generated `src/schemas/<name>.py` and call `database.register(...)` for the types listed in `specs/systems/<name>/readme.md`'s `tables: [...]`.
5. For each system, instantiate its parser and run `parser.scan()` / `parser.parse(...)` to seed the database.
6. Walk `src/routes/<system>/<op>/route.py` modules and register each handler.
7. Start `vault/debounce.py`'s watcher loop.
8. Wrap the FastAPI app with `FastMCP.from_fastapi(...)` so every route is automatically exposed as an MCP tool.
9. Serve.

## Degraded mode

The server depends on Obsidian being running to discover the active vault root. If the Obsidian CLI is unavailable or no vault is configured at startup, the server still binds and serves rather than exiting:

- Logging is initialized normally so the failure is recorded.
- The FastAPI app and MCP wrapper are built and routes are registered, but the database is not seeded and the watcher is not started.
- Vault-dependent endpoints respond with HTTP 503 until initialization completes.
- A background retry loop re-probes Obsidian on a fixed interval; once the vault becomes reachable, the normal startup steps (register tables, parse, start watcher) run and the server transitions out of degraded mode without a restart.
- The retry loop exits cleanly on shutdown.

## Configuration

Vault root and other deployment-time settings come from environment variables / a config file consumed by `server.py`. The database, parsers, and routes do not read environment directly; `server.py` injects what they need.

## Shutdown

On shutdown, the watcher loop is cancelled, any pending debounced writes are flushed, and the database is closed.
