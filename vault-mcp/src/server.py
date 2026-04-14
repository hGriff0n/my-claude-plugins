"""
Vault MCP Server entry point.

Startup sequence:
1. Read VAULT_ROOT and EXCLUDE_DIRS from environment
2. Initialize VaultCache (full vault scan)
3. Start cache background worker thread
4. Start VaultWatcher daemon thread
5. Build FastAPI app with REST routes
6. Create MCP server from FastAPI app (auto-generates MCP tools)
7. Mount REST at /app, MCP at /mcp on a single parent app
"""

import logging
import logging.handlers
from datetime import datetime
import os
import sys
from pathlib import Path
import uvicorn

from fastapi import FastAPI
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

from api.deps import set_cache
from api.routes import router
from cache.vault_cache import VaultCache
from utils.obsidian import obsidian_cli
from watcher.vault_watcher import VaultWatcher

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)

_log_file = _log_dir / f"server_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        h for h in [
            logging.StreamHandler(sys.stderr) if sys.stderr else None,
            logging.handlers.TimedRotatingFileHandler(
                _log_file, when="midnight", backupCount=14,
            ),
        ] if h is not None
    ],
)
log = logging.getLogger(__name__)


def _parse_exclude_dirs(raw: str) -> set[str]:
    """Parse a comma-separated list of directory names to exclude."""
    return {part.strip() for part in raw.split(",") if part.strip()}


def create_app() -> FastAPI:
    """Build the FastAPI application with all routes."""
    app = FastAPI(
        title="vault-mcp",
        docs_url="/docs",
        openapi_url="/openapi.json",
        redirect_slashes=False
    )
    app.include_router(router)
    return app


def main() -> None:
    r = obsidian_cli("vault", "info=path")
    if r.returncode != 0:
        log.error("obsidian CLI not available or no vault configured: %s", r.stderr.strip())
        sys.exit(1)

    vault_root = Path(r.stdout.strip())
    if not vault_root.is_dir():
        log.error("Vault path does not exist or is not a directory: %s", vault_root)
        sys.exit(1)

    exclude_raw = os.environ.get("EXCLUDE_DIRS", ".git,.obsidian,node_modules,.trash")
    exclude_dirs = _parse_exclude_dirs(exclude_raw)

    log.info("Vault root: %s", vault_root)
    log.info("Excluded dirs: %s", exclude_dirs)

    # Initialize cache and perform full vault scan
    cache = VaultCache()
    log.info("Scanning vault...")
    cache.initialize(vault_root, exclude_dirs)
    log.info("Vault scan complete")

    # Start background worker that drains the update queue
    cache.start_worker()

    # Start file system watcher
    watcher = VaultWatcher(cache, vault_root, exclude_dirs)
    watcher.start()

    # Wire cache into the dependency provider, then build REST and MCP sub-apps
    set_cache(cache)
    rest_app = create_app()
    mcp = FastMCP.from_fastapi(app=rest_app)

    @mcp.tool("task_archive")
    def task_archive(dry_run: bool = False) -> dict:
        """Archive completed tasks to daily notes.

        Finds all completed tasks, groups them by completion date, writes them
        to the appropriate daily note files, and removes them from the source
        task files. Done parents with open children are reopened with a
        blocking reference to their open subtasks.

        Args:
            dry_run: If True, report what tasks would be archived without
                     actually moving or modifying any files.
        """
        from scripts.archive_tasks import archive_tasks

        api_port = int(os.environ.get("API_PORT", "9400"))
        api_base = f"http://localhost:{api_port}"
        return archive_tasks(cache, api_base=api_base, dry_run=dry_run)

    mcp_asgi = mcp.http_app(transport="streamable-http", path="/mcp")

    # Parent app: mounts both, carries MCP lifespan + CORS
    app = FastAPI(
        title="vault-mcp",
        redirect_slashes=False,
        lifespan=mcp_asgi.lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/app", rest_app)
    app.mount("/", mcp_asgi)

    api_port = int(os.environ.get("API_PORT", "9400"))
    log.info("Starting vault-mcp server on port %d", api_port)

    config = uvicorn.Config(app, port=api_port, log_level="info")
    server = uvicorn.Server(config)

    global _server
    _server = server

    try:
        server.run()
    except Exception as e:
        log.error("Exception: %s", e)
    finally:
        _server = None
        watcher.stop()
        cache.stop_worker()


_server: uvicorn.Server | None = None


def shutdown() -> None:
    """Signal the uvicorn server to exit gracefully."""
    if _server is not None:
        _server.should_exit = True
    log.info('Received shutdown signal')


if __name__ == "__main__":
    main()
