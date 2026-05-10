"""
Effort parser.

Implements the parser surface from `specs/arch/parser.md` for the efforts
system (`specs/systems/efforts/readme.md`). An effort is a folder under
`efforts/` containing `00 README.md`, `CLAUDE.md`, and `01 TASKS.md`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

import yaml

from schemas.efforts import DisplayDetails, Effort, EffortStatus, TaskStats
from schemas.tasks import TaskStatus
from schemas.time import TimeBlock
from vault.parser import Parser
from vault.watcher import EventType, WatchCriterion, WatcherHandle

log = logging.getLogger(__name__)

SYSTEM_NAME = "efforts"
EFFORTS_DIR = "efforts"
BACKLOG_DIR = "__backlog"
IDEAS_DIR = "__ideas"
REQUIRED_FILES = ("00 README.md", "CLAUDE.md", "01 TASKS.md")

MoveTarget = Literal["active", "backlog", "archive"]


@dataclass(frozen=True)
class CreateEffort:
    """Scaffold a new active effort with templated files."""


@dataclass(frozen=True)
class MoveEffort:
    """Move an effort between active, backlog, and archive."""

    target: MoveTarget


Update = Union[CreateEffort, MoveEffort]


def _is_effort_folder(folder: Path) -> bool:
    return folder.is_dir() and all((folder / f).exists() for f in REQUIRED_FILES)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return {}, text
    end: Optional[int] = None
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            end = j
            break
    if end is None:
        return {}, text
    fm = yaml.safe_load("\n".join(lines[i + 1 : end])) or {}
    body = "\n".join(lines[end + 1 :])
    return (fm if isinstance(fm, dict) else {}), body


def _first_paragraph_after_title(body: str) -> str:
    lines = body.splitlines()
    i = 0
    n = len(lines)
    while i < n and not lines[i].strip():
        i += 1
    if i < n and lines[i].lstrip().startswith("#"):
        i += 1
    while i < n and not lines[i].strip():
        i += 1
    paragraph: list[str] = []
    while i < n and lines[i].strip():
        paragraph.append(lines[i].strip())
        i += 1
    return " ".join(paragraph)


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


EffortParserInterface = Parser[Effort, Update]
class EffortParser:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root)
        self._db: Any = None
        self._watcher: Any = None
        self._task_parser: Any = None
        self._effort_handles: dict[Path, WatcherHandle] = {}

    @property
    def _efforts_root(self) -> Path:
        return self.vault_root / EFFORTS_DIR

    @property
    def _backlog_root(self) -> Path:
        return self._efforts_root / BACKLOG_DIR

    def attach_task_parser(self, task_parser: Any) -> None:
        """Wire up the task parser so parse() can register task watchers."""
        self._task_parser = task_parser

    # ---- initialize ----

    def initialize(self, db: Any, watcher: Any) -> None:
        self._db = db
        self._watcher = watcher

        events = frozenset({EventType.CREATE, EventType.MODIFY, EventType.DELETE})
        self._efforts_root.mkdir(parents=True, exist_ok=True)
        watcher.register(
            WatchCriterion(target=self._efforts_root, events=events),
            self._on_root_event,
        )
        # Backlog root may not exist yet; register lazily on first appearance.
        watcher.register(
            WatchCriterion(target=self._backlog_root, events=events),
            self._on_root_event,
        )

    def _elements_for_file(self, folder: Path) -> List[Effort]:
        try:
            rel = folder.relative_to(self.vault_root).as_posix()
        except ValueError:
            return []
        return [
            e for e in self._db.query('SELECT * FROM "effort"')
            if e.path.as_posix() == rel
        ]

    def _on_root_event(
        self, file: Path, event: EventType, handle: WatcherHandle,
    ) -> None:
        if event == EventType.DELETE or not file.is_dir():
            return
        for child in sorted(file.iterdir()):
            if child.name in (BACKLOG_DIR, IDEAS_DIR):
                continue
            if _is_effort_folder(child):
                self._register_effort(child)

    def _register_effort(self, folder: Path) -> None:
        events = frozenset({EventType.MODIFY, EventType.DELETE})
        handle = self._watcher.register(
            WatchCriterion(target=folder, events=events),
            self._on_effort_event,
        )
        self._effort_handles[folder] = handle

    def _on_effort_event(
        self, file: Path, event: EventType, handle: WatcherHandle,
    ) -> None:
        if event == EventType.DELETE:
            elements = self._elements_for_file(file)
            for effort in elements:
                self._db.delete(effort)
            self._effort_handles.pop(file, None)
            return
        for effort in self.parse(file):
            self._db.update(effort)
            if self._task_parser is not None:
                taskfile = file / "01 TASKS.md"
                if taskfile.is_file():
                    self._task_parser.register_taskfile(taskfile)

    # ---- parse ----

    def parse(self, folder: Path) -> list[Effort]:
        folder = Path(folder)
        if not _is_effort_folder(folder):
            return []

        name = folder.name
        rel_path = folder.relative_to(self.vault_root).as_posix()
        status = (
            EffortStatus.BACKLOG
            if folder.parent.name == BACKLOG_DIR
            else EffortStatus.ACTIVE
        )

        readme = folder / "00 README.md"
        readme_text = readme.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(readme_text)
        description = _first_paragraph_after_title(body)

        due = _coerce_date(frontmatter.get("due"))
        scheduled = _coerce_date(frontmatter.get("scheduled"))

        required_paths = [folder / f for f in REQUIRED_FILES]
        all_files = [p for p in folder.rglob("*") if p.is_file()]
        mtimes = [p.stat().st_mtime for p in all_files]
        created_ts = min(mtimes) if mtimes else folder.stat().st_mtime
        last_updated_ts = max(p.stat().st_mtime for p in required_paths)

        time_details = TimeBlock(
            created=date.fromtimestamp(created_ts),
            last_updated=date.fromtimestamp(last_updated_ts),
            due=due,
            scheduled=scheduled,
        )

        zero_stats = {s.value: 0 for s in TaskStatus}
        display = DisplayDetails(task_stats=TaskStats(num_by_status=zero_stats))

        return [
            Effort(
                name=name,
                path=Path(rel_path),
                status=status,
                description=description,
                time_details=time_details,
                display=display,
            )
        ]

    # ---- update (DB only) ----

    def update(self, effort: Effort, op: Update) -> None:
        if isinstance(op, CreateEffort):
            self._db.update(effort)
            return
        if isinstance(op, MoveEffort):
            new_path = self._target_path(effort.name, op.target).relative_to(
                self.vault_root,
            )
            effort.path = Path(new_path.as_posix())
            effort.status = (
                EffortStatus.BACKLOG if op.target == "backlog"
                else EffortStatus.ACTIVE
            )
            if op.target == "archive":
                self._db.delete(effort)
            else:
                self._db.update(effort)
            return
        raise TypeError(f"Unknown Update: {op!r}")

    def _target_path(self, name: str, target: str) -> Path:
        if target == "backlog":
            return self._backlog_root / name
        return self._efforts_root / name

