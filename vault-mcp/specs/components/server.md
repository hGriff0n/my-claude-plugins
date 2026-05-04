# Server Component

The process entrypoint. Wires up the database, parsers, and routes, and exposes the result as both a REST API (FastAPI) and an MCP server (FastMCP).

## Layout

- `src/server.py` — entrypoint. Creates the FastAPI app, registers tables, runs initial scans, and starts the watcher.
- `src/routes/server.py` — walks `src/routes/<system>/<op>/route.py` files and registers each handler into the FastAPI app (see `arch/routes.md` Aggregation).

## Startup sequence

1. Construct the FastAPI app.
2. For each system, import its generated `src/schemas/<name>.py` and call `database.register(...)` for the types listed in `specs/systems/<name>/readme.md`'s `tables: [...]`.
3. For each system, instantiate its parser and run `parser.scan()` / `parser.parse(...)` to seed the database.
4. Walk `src/routes/<system>/<op>/route.py` modules and register each handler.
5. Start `vault/debounce.py`'s watcher loop.
6. Wrap the FastAPI app with `FastMCP.from_fastapi(...)` so every route is automatically exposed as an MCP tool.
7. Serve.

## Configuration

Vault root and other deployment-time settings come from environment variables / a config file consumed by `server.py`. The database, parsers, and routes do not read environment directly; `server.py` injects what they need.

## Shutdown

On shutdown, the watcher loop is cancelled, any pending debounced writes are flushed, and the database is closed.
