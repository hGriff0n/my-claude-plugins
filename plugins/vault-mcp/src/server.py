"""
Vault MCP Server entry point.

Startup sequence:
1. Read VAULT_ROOT and EXCLUDE_DIRS from environment
2. Initialize VaultCache (full vault scan)
3. Start cache background worker thread
4. Start VaultWatcher daemon thread
5. Register all MCP tools
6. Start REST API server in background thread (if API_ENABLED)
7. Run MCP server (stdio transport)
"""

import logging
import os
import sys
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cache.vault_cache import VaultCache
from tools import register_effort_tools, register_task_tools
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


def _start_api_server(cache, port: int) -> None:
    """Run the FastAPI/uvicorn server in a daemon thread."""
    import uvicorn

    from api.app import create_app

    app = create_app(cache)
    log.info("Starting REST API on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main() -> None:
    vault_root_env = os.environ.get("VAULT_ROOT", "")
    if not vault_root_env:
        log.error("VAULT_ROOT environment variable is not set")
        sys.exit(1)

    vault_root = Path(vault_root_env)
    if not vault_root.is_dir():
        log.error("VAULT_ROOT does not exist or is not a directory: %s", vault_root)
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

    # Start REST API in a daemon thread
    api_enabled = os.environ.get("API_ENABLED", "true").lower() in ("true", "1", "yes")
    if api_enabled:
        api_port = int(os.environ.get("API_PORT", "9400"))
        api_thread = threading.Thread(
            target=_start_api_server, args=(cache, api_port), daemon=True
        )
        api_thread.start()

    # Create MCP server and register tools
    mcp = FastMCP("vault-mcp")
    register_task_tools(mcp, cache)
    register_effort_tools(mcp, cache)

    log.info("Starting vault-mcp server")
    try:
        mcp.run(transport="stdio")
    finally:
        watcher.stop()
        cache.stop_worker()


if __name__ == "__main__":
    main()
