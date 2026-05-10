"""
Vault MCP Server entry point.

Implements `specs/components/server.md`. Wires the database, watcher,
write debouncer, and parsers, then exposes the FastAPI app as both REST
and an MCP server via `FastMCP.from_fastapi`.
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
from routes.deps import App, set_app
from routes.routes import router as api_router
from schemas.efforts import Effort
from schemas.tasks import Task
from utils.obsidian import obsidian_cli
from vault.debounce import WriteDebouncer
from vault.efforts.parser import EffortParser
from vault.tasks.parser import TaskParser
from vault.watcher import Watcher

VAULT_INIT_RETRY_SECONDS = 30

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

# Step 1: logging
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

WAL_PATH = _log_dir / "pending_writes.jsonl"
DB_PATH = _log_dir / "vault-mcp.db"


_state: dict = {"parsers_initialized": False}
_state_lock = threading.Lock()
_server: uvicorn.Server | None = None


def _probe_vault_root() -> Path | None:
    r = obsidian_cli("vault", "info=path")
    if r.returncode != 0:
        log.warning("obsidian CLI unavailable or no vault: %s", r.stderr.strip())
        return None
    vault_root = Path(r.stdout.strip())
    if not vault_root.is_dir():
        log.warning("Vault path missing: %s", vault_root)
        return None
    return vault_root


def _initialize_parsers(
    db: Database,
    watcher: Watcher,
    debouncer: WriteDebouncer,
    vault_root: Path,
) -> tuple[EffortParser, TaskParser]:
    """Step 6 — parser initialization (deferred in degraded mode)."""
    effort_parser = EffortParser(vault_root)
    task_parser = TaskParser(vault_root)
    effort_parser.attach_task_parser(task_parser)

    # Tasks initialize first so the effort parser's seed callbacks can
    # call task_parser.register_taskfile (it needs an attached watcher).
    task_parser.initialize(db, watcher, debouncer)
    effort_parser.initialize(db, watcher, debouncer)

    debouncer.wal_replay(db)
    return effort_parser, task_parser


def _vault_init_retry_loop(
    db: Database,
    watcher: Watcher,
    debouncer: WriteDebouncer,
    rest_app: FastAPI,
) -> None:
    while True:
        with _state_lock:
            if _state["parsers_initialized"]:
                return
        if _server is None or _server.should_exit:
            return
        time.sleep(VAULT_INIT_RETRY_SECONDS)
        if _server is None or _server.should_exit:
            return
        log.info("Retrying parser initialization...")
        vault_root = _probe_vault_root()
        if vault_root is None:
            continue
        try:
            effort_parser, task_parser = _initialize_parsers(
                db, watcher, debouncer, vault_root,
            )
        except Exception:
            log.exception("Deferred parser init failed")
            continue
        set_app(App(db=db, effort_parser=effort_parser, task_parser=task_parser))
        watcher.start()
        debouncer.start()
        with _state_lock:
            _state["parsers_initialized"] = True
        log.info("Parser init complete; degraded mode lifted")
        return


def main() -> None:
    # Step 2: FastAPI app
    rest_app = FastAPI(
        title="vault-mcp",
        docs_url="/docs",
        openapi_url="/openapi.json",
        redirect_slashes=False,
    )

    # Step 3: database, watcher, debouncer
    db = Database(path=str(DB_PATH))
    watcher = Watcher()
    debouncer = WriteDebouncer(watcher=watcher, wal_path=WAL_PATH)
    db.attach_debouncer(debouncer)

    # Step 4: register tables for every system (Obsidian-independent)
    db.register(Effort, system="efforts")
    db.register(Task, system="tasks")

    # Step 5: probe Obsidian
    vault_root = _probe_vault_root()

    # Step 6: parser initialization (deferred if Obsidian unavailable)
    effort_parser: EffortParser | None = None
    task_parser: TaskParser | None = None
    if vault_root is not None:
        try:
            effort_parser, task_parser = _initialize_parsers(
                db, watcher, debouncer, vault_root,
            )
            with _state_lock:
                _state["parsers_initialized"] = True
            log.info("Vault root: %s", vault_root)
        except Exception:
            log.exception("Parser initialization failed; entering degraded mode")
            effort_parser = task_parser = None

    if effort_parser is not None and task_parser is not None:
        set_app(App(db=db, effort_parser=effort_parser, task_parser=task_parser))

    # Step 7: routes
    rest_app.include_router(api_router)

    # Step 8: start watcher + debouncer loops (only if initialized)
    if _state["parsers_initialized"]:
        watcher.start()
        debouncer.start()
    else:
        log.warning(
            "Degraded mode: vault-dependent endpoints will return 503 until "
            "Obsidian becomes reachable.",
        )

    # Step 9: wrap with FastMCP
    mcp = FastMCP.from_fastapi(app=rest_app)
    mcp_asgi = mcp.http_app(transport="streamable-http", path="/mcp")

    app = FastAPI(
        title="vault-mcp",
        redirect_slashes=False,
        lifespan=mcp_asgi.lifespan,
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/app", rest_app)
    app.mount("/", mcp_asgi)

    # Step 10: serve
    api_port = int(os.environ.get("API_PORT", "9400"))
    log.info("Starting vault-mcp server on port %d", api_port)

    config = uvicorn.Config(app, port=api_port, log_level="info")
    server = uvicorn.Server(config)
    global _server
    _server = server

    if not _state["parsers_initialized"]:
        threading.Thread(
            target=_vault_init_retry_loop,
            args=(db, watcher, debouncer, rest_app),
            name="vault-init-retry",
            daemon=True,
        ).start()

    try:
        server.run()
    except Exception as e:
        log.error("Exception: %s", e)
    finally:
        try:
            debouncer.stop()
            watcher.stop()
        except Exception:
            log.exception("Error during shutdown")
        _server = None


def shutdown() -> None:
    if _server is not None:
        _server.should_exit = True
    log.info("Received shutdown signal")


if __name__ == "__main__":
    main()
