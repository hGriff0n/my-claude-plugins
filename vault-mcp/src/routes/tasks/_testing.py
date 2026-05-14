"""Shared test helpers for task route tests."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from database import Database  # noqa: E402
from routes.deps import App, set_app  # noqa: E402
from schemas.efforts import Effort  # noqa: E402
from schemas.tasks import Task  # noqa: E402
from vault.efforts.parser import EffortParser  # noqa: E402
from vault.tasks.parser import ROOT_TASKFILE, TaskParser  # noqa: E402
from vault.watcher import Watcher  # noqa: E402


def make_vault(tmp_path: Path) -> Path:
    (tmp_path / "efforts").mkdir()
    (tmp_path / ROOT_TASKFILE).write_text("", encoding="utf-8")
    return tmp_path


def make_effort_folder(vault: Path, name: str, *, backlog: bool = False) -> Path:
    parent = vault / "efforts" / "__backlog" if backlog else vault / "efforts"
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "00 README.md").write_text(f"# {name}\n", encoding="utf-8")
    (folder / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    (folder / ROOT_TASKFILE).write_text("", encoding="utf-8")
    return folder


def make_client(vault: Path, router) -> tuple[TestClient, App]:
    db = Database()
    db.register(Effort, system="efforts")
    db.register(Task, system="tasks")

    watcher = Watcher()

    effort_parser = EffortParser(vault)
    task_parser = TaskParser(vault)
    effort_parser.attach_task_parser(task_parser)
    task_parser.initialize(db, watcher)
    effort_parser.initialize(db, watcher)

    app_ctx = App(db=db, effort_parser=effort_parser, task_parser=task_parser)
    set_app(app_ctx)

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return TestClient(fastapi_app), app_ctx
