"""
Vault MCP Server entry point.

Startup sequence:
1. Read VAULT_ROOT and EXCLUDE_DIRS from environment
2. Initialize VaultCache (full vault scan)
3. Start cache background worker thread
4. Start VaultWatcher daemon thread
5. Build FastAPI app with REST routes
6. Create MCP server from FastAPI app (auto-generates MCP tools)
7. Run REST on API_PORT, MCP on API_PORT+1
"""

import logging
import os
import sys
import threading
from pathlib import Path
import uvicorn

from fastapi import APIRouter, FastAPI
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from api.routes import register_routes
from cache.vault_cache import VaultCache
from utils.obsidian import obsidian_cli
from watcher.vault_watcher import VaultWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def _parse_exclude_dirs(raw: str) -> set[str]:
    """Parse a comma-separated list of directory names to exclude."""
    return {part.strip() for part in raw.split(",") if part.strip()}


def create_app(cache) -> FastAPI:
    """Build the FastAPI application with all routes bound to the cache."""
    app = FastAPI(
        title="vault-mcp",
        docs_url="/docs",
        openapi_url="/openapi.json",
        redirect_slashes=False
    )
    api = APIRouter()
    register_routes(api, cache)
    app.include_router(api)
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
    # cache.start_worker()

    # Start file system watcher

    watcher = VaultWatcher(cache, vault_root, exclude_dirs)
    # watcher.start()

    # Build FastAPI app and create MCP server from it
    rest_app = create_app(cache)
    mcp = FastMCP.from_fastapi(app=rest_app)

    # Wrap MCP in a FastAPI app with CORS so browser-based clients
    # (MCP Inspector) can pass OPTIONS preflight checks
    mcp_asgi = mcp.http_app(transport="streamable-http")
    mcp_app = FastAPI(lifespan=mcp_asgi.lifespan)
    mcp_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    mcp_app.mount("/", mcp_asgi)

    api_port = int(os.environ.get("API_PORT", "9400"))
    mcp_port = api_port + 1

    # Run REST and MCP on separate ports
    def run_rest():
        log.info("Starting REST server on port %d", api_port)
        uvicorn.run(rest_app, port=api_port, log_level="info")

    rest_thread = threading.Thread(target=run_rest, daemon=True)
    rest_thread.start()

    log.info("Starting MCP server on port %d", mcp_port)
    try:
        uvicorn.run(mcp_app, port=mcp_port, log_level="info")
    finally:
        watcher.stop()
        cache.stop_worker()


if __name__ == "__main__":
    main()
