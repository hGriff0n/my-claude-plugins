"""
Effort parser.

Implements the parser surface from `specs/arch/parser.md` for the efforts
system (`specs/systems/efforts/readme.md`). An effort is a folder under
`efforts/` containing `00 README.md`, `CLAUDE.md`, and `01 TASKS.md`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Optional, Union

import yaml

from schemas.efforts import DisplayDetails, Effort, EffortStatus, TaskStats
from schemas.tasks import TaskStatus
from schemas.time import TimeBlock
from utils.obsidian import obsidian_cli

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


class EffortParser:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root)

    @property
    def _efforts_root(self) -> Path:
        return self.vault_root / EFFORTS_DIR

    @property
    def _backlog_root(self) -> Path:
        return self._efforts_root / BACKLOG_DIR

    # ---- scan ----

    def scan(self) -> list[Path]:
        results: list[Path] = []
        if not self._efforts_root.is_dir():
            return results
        for child in sorted(self._efforts_root.iterdir()):
            if child.name == BACKLOG_DIR:
                continue
            if _is_effort_folder(child):
                results.append(child)
        if self._backlog_root.is_dir():
            for child in sorted(self._backlog_root.iterdir()):
                if _is_effort_folder(child):
                    results.append(child)
        return results

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

    # ---- write ----

    def write(self, effort: Effort, update: Update) -> None:
        if isinstance(update, CreateEffort):
            self._create(effort.name)
            return
        if isinstance(update, MoveEffort):
            self._move(effort.name, update.target)
            return
        raise TypeError(f"Unknown Update: {update!r}")

    def _create(self, name: str) -> None:
        target = self._efforts_root / name
        backlog = self._backlog_root / name
        if _is_effort_folder(target) or _is_effort_folder(backlog):
            raise FileExistsError(f"Effort already exists: {name}")

        ideas_placeholder = self._efforts_root / IDEAS_DIR / name
        nested_dest = target / name

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

        templates = [
            ("efforts/claude", "CLAUDE.md"),
            ("efforts/readme", "00 README.md"),
            ("efforts/taskfile", "01 TASKS.md"),
        ]
        for template, filename in templates:
            rel = (target / filename).relative_to(self.vault_root).as_posix()
            res = obsidian_cli("create", f"template={template}", f'path="{rel}"')
            if res.returncode != 0:
                raise RuntimeError(
                    f"obsidian_cli create failed for {rel}: {res.stderr.strip()}"
                )

    def _move(self, name: str, target: MoveTarget) -> None:
        active_path = self._efforts_root / name
        backlog_path = self._backlog_root / name

        if _is_effort_folder(active_path):
            current = active_path
            current_state: MoveTarget = "active"
        elif _is_effort_folder(backlog_path):
            current = backlog_path
            current_state = "backlog"
        else:
            raise FileNotFoundError(f"Effort not found: {name}")

        if target == current_state:
            return

        if target == "active":
            shutil.move(str(current), str(active_path))
        elif target == "backlog":
            self._backlog_root.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(backlog_path))
        elif target == "archive":
            shutil.rmtree(current)
        else:
            raise ValueError(f"Unknown move target: {target}")
