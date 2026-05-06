"""
Effort parser.

Implements the parser surface from `specs/arch/parser.md` for the efforts
system (`specs/systems/efforts/readme.md`). An effort is a folder under
`efforts/` containing `00 README.md`, `CLAUDE.md`, and `01 TASKS.md`.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

import yaml

from schemas.efforts import DisplayDetails, Effort, EffortStatus, TaskStats
from schemas.tasks import TaskStatus
from schemas.time import TimeBlock
from utils.obsidian import obsidian_cli
from vault.parser import Parser
from vault.watcher import EventType, WatchCriterion, WatcherHandle, active_origin

log = logging.getLogger(__name__)

SYSTEM_NAME = "efforts"
EFFORTS_DIR = "efforts"
BACKLOG_DIR = "__backlog"
IDEAS_DIR = "__ideas"
REQUIRED_FILES = ("00 README.md", "CLAUDE.md", "01 TASKS.md")

_NULL_DATE = date.min

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
        self._debouncer: Any = None
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

    def initialize(self, db: Any, watcher: Any, debouncer: Any) -> None:
        self._db = db
        self._watcher = watcher
        self._debouncer = debouncer
        debouncer.register_system(
            name=SYSTEM_NAME,
            lag=timedelta(0),
            parent_file_resolver=self._parent_file,
            writer=self.write,
            elements_for_file=self._elements_for_file,
            models={Effort.__name__: Effort},
        )

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

    def _parent_file(self, effort: Effort) -> Path:
        return self.vault_root / effort.path

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
                self._db.delete(effort, origin=handle)
            self._effort_handles.pop(file, None)
            return
        for effort in self.parse(file):
            self._db.update(effort, origin=handle)
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

        due = _coerce_date(frontmatter.get("due")) or _NULL_DATE
        scheduled = _coerce_date(frontmatter.get("scheduled")) or _NULL_DATE

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
            self._db.update(effort, origin=active_origin())
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
                self._db.delete(effort, origin=active_origin())
            else:
                self._db.update(effort, origin=active_origin())
            return
        raise TypeError(f"Unknown Update: {op!r}")

    # ---- write (DB → file projection) ----

    def write(self, file: Path, elements: List[Effort]) -> None:
        if not elements:
            if file.is_dir():
                shutil.rmtree(file)
            return
        if len(elements) > 1:
            raise ValueError(
                f"Multiple efforts projected to one folder: {file}",
            )
        [effort] = elements
        target = self.vault_root / effort.path
        if file != target:
            log.warning("write target %s != effort path %s", file, target)
        if not _is_effort_folder(target):
            self._scaffold(target)
            return
        # Already a complete effort folder at the right location — nothing to do.

    def _target_path(self, name: str, target: str) -> Path:
        if target == "backlog":
            return self._backlog_root / name
        return self._efforts_root / name

    def _scaffold(self, target: Path) -> None:
        backlog_alt = self._backlog_root / target.name
        active_alt = self._efforts_root / target.name
        existing: Optional[Path] = None
        if _is_effort_folder(active_alt) and active_alt != target:
            existing = active_alt
        elif _is_effort_folder(backlog_alt) and backlog_alt != target:
            existing = backlog_alt
        if existing is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(existing), str(target))
            return

        ideas_placeholder = self._efforts_root / IDEAS_DIR / target.name
        nested_dest = target / target.name

        if target.exists() and not _is_effort_folder(target):
            entries = [e for e in target.iterdir() if e != nested_dest]
            if entries:
                nested_dest.mkdir(parents=True, exist_ok=True)
                for entry in entries:
                    shutil.move(str(entry), str(nested_dest / entry.name))
        elif ideas_placeholder.exists():
            target.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ideas_placeholder), str(nested_dest))
        else:
            target.mkdir(parents=True, exist_ok=True)

        template_base = "newnotes/efforts"
        templates = [
            ("claude", "CLAUDE"),
            ("readme", "00 README"),
            ("taskfile", "01 TASKS"),
        ]
        for template, filename in templates:
            rel = (target / filename).relative_to(self.vault_root).as_posix()
            res = obsidian_cli(
                "create", f"template={template_base}/{template}", f"path={rel}",
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"obsidian_cli create failed for {rel}: {res.stderr.strip()}"
                )

