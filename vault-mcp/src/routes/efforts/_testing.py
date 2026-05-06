"""Shared test helpers for efforts route tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Allow `from schemas...` and friends to resolve when tests run via pytest.
_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from database import Database  # noqa: E402
from routes.deps import App, set_app  # noqa: E402
from schemas.efforts import Effort  # noqa: E402
from schemas.tasks import Task  # noqa: E402
from vault.debounce import WriteDebouncer  # noqa: E402
from vault.efforts.parser import EffortParser  # noqa: E402
from vault.tasks.parser import TaskParser  # noqa: E402
from vault.watcher import Watcher  # noqa: E402

REQUIRED_FILES = ("00 README.md", "CLAUDE.md", "01 TASKS.md")


def make_vault(tmp_path: Path) -> Path:
    (tmp_path / "efforts").mkdir()
    return tmp_path


def make_effort_folder(
    vault: Path, *parts: str, body: str = "", frontmatter: str = ""
) -> Path:
    folder = vault.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "00 README.md"
    if frontmatter:
        readme.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    else:
        readme.write_text(body, encoding="utf-8")
    (folder / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    (folder / "01 TASKS.md").write_text("tasks\n", encoding="utf-8")
    return folder


def make_client(vault: Path, router) -> tuple[TestClient, App]:
    db = Database()
    db.register(Effort, system="efforts")
    db.register(Task, system="tasks")

    watcher = Watcher()
    debouncer = WriteDebouncer(watcher=watcher, wal_path=vault / ".vault-mcp.wal")
    db.attach_debouncer(debouncer)

    effort_parser = EffortParser(vault)
    task_parser = TaskParser(vault)
    effort_parser.attach_task_parser(task_parser)
    task_parser.initialize(db, watcher, debouncer)
    effort_parser.initialize(db, watcher, debouncer)

    app_ctx = App(db=db, effort_parser=effort_parser, task_parser=task_parser)
    set_app(app_ctx)

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return TestClient(fastapi_app), app_ctx


def fake_obsidian_create(vault: Path):
    """Stub obsidian_cli that materializes templated files in `vault`.

    Mirrors obsidian's behavior of appending `.md` to the path arg when
    creating from a template.
    """

    def fake(*args: str) -> Mock:
        if args and args[0] == "create":
            path_arg = next((a for a in args[1:] if a.startswith("path=")), None)
            if path_arg:
                rel = path_arg[len("path=") :].strip().strip('"')
                if not rel.endswith(".md"):
                    rel += ".md"
                target = vault / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("", encoding="utf-8")
                return Mock(returncode=0, stdout=f"Created: {rel}", stderr="")
        return Mock(returncode=0, stdout="", stderr="")

    return fake
