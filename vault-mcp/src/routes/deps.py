"""Shared App context for routes.

A single `App` holds the database and per-system parsers. Routes resolve
their dependencies via `get_app()` and read members off that.
"""

from dataclasses import dataclass

from fastapi import HTTPException

from database import Database
from vault.efforts.parser import EffortParser
from vault.tasks.parser import TaskParser


@dataclass
class App:
    db: Database
    effort_parser: EffortParser
    task_parser: TaskParser


_app: App | None = None


def set_app(app: App) -> None:
    global _app
    _app = app


def get_app() -> App:
    if _app is None:
        raise HTTPException(status_code=503, detail="App not initialized")
    return _app
