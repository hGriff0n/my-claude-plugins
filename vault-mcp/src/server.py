"""
Vault MCP Server entry point.

Implements `specs/components/server.md`. Wires the database, parsers, and
(future) routes, then exposes the FastAPI app as both REST and an MCP server
via `FastMCP.from_fastapi`. Routes are not registered yet.
"""

import logging
import logging.handlers
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

from database import Database
from schemas.efforts import Effort
from utils.obsidian import obsidian_cli
from vault.efforts.parser import EffortParser

VAULT_INIT_RETRY_SECONDS = 30

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


_state: dict = {"db": None, "vault_root": None, "initialized": False}
_state_lock = threading.Lock()
_server: uvicorn.Server | None = None


def _probe_vault_root() -> Path | None:
    """Ask Obsidian for the active vault path. Returns None if unavailable."""
    r = obsidian_cli("vault", "info=path")
    if r.returncode != 0:
        log.warning("obsidian CLI not available or no vault configured: %s", r.stderr.strip())
        return None
    vault_root = Path(r.stdout.strip())
    if not vault_root.is_dir():
        log.warning("Vault path does not exist or is not a directory: %s", vault_root)
        return None
    return vault_root


def _seed_efforts(db: Database, vault_root: Path) -> None:
    parser = EffortParser(vault_root)
    count = 0
    for folder in parser.scan():
        for effort in parser.parse(folder):
            db.update(effort, effort)
            count += 1
    log.info("Seeded %d efforts", count)


def _initialize_vault(db: Database) -> bool:
    """Probe Obsidian, register tables, and seed the database."""
    with _state_lock:
        if _state["initialized"]:
            return True

        vault_root = _probe_vault_root()
        if vault_root is None:
            return False

        log.info("Vault root: %s", vault_root)

        db.register(Effort, system="efforts")
        _seed_efforts(db, vault_root)

        _state["vault_root"] = vault_root
        _state["initialized"] = True
        log.info("Vault initialization complete")
        return True


def _vault_init_retry_loop(db: Database) -> None:
    """Background retry until Obsidian becomes available."""
    while True:
        if _state["initialized"]:
            return
        if _server is None or _server.should_exit:
            return
        time.sleep(VAULT_INIT_RETRY_SECONDS)
        if _server is None or _server.should_exit:
            return
        log.info("Retrying vault initialization...")
        if _initialize_vault(db):
            return


def main() -> None:
    db = Database()
    _state["db"] = db

    rest_app = FastAPI(
        title="vault-mcp",
        docs_url="/docs",
        openapi_url="/openapi.json",
        redirect_slashes=False,
    )

    initialized = _initialize_vault(db)
    if not initialized:
        log.warning(
            "Starting server in degraded mode. Vault-dependent endpoints will "
            "return 503 until Obsidian is running."
        )

    mcp = FastMCP.from_fastapi(app=rest_app)
    mcp_asgi = mcp.http_app(transport="streamable-http", path="/mcp")

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

    if not initialized:
        threading.Thread(
            target=_vault_init_retry_loop,
            args=(db,),
            name="vault-init-retry",
            daemon=True,
        ).start()

    try:
        server.run()
    except Exception as e:
        log.error("Exception: %s", e)
    finally:
        _server = None


def shutdown() -> None:
    """Signal the uvicorn server to exit gracefully."""
    if _server is not None:
        _server.should_exit = True
    log.info("Received shutdown signal")


if __name__ == "__main__":
    main()
