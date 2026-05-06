"""
Task parser.

Implements the parser surface from `specs/arch/parser.md` for the tasks
system (`specs/systems/tasks/readme.md`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import emoji

from schemas.tasks import Dependencies, Task, TaskStatus, TaskType
from schemas.time import TimeBlock
from utils.formatting import EMOJI_TO_TAG, render_tags
from utils.ids import generate_task_id
from vault.efforts.parser import BACKLOG_DIR, EFFORTS_DIR, EffortParser

ROOT_TASKFILE = "01 TASKS.md"

_NULL_DATE = date.min

# Tags that carry model-field semantics rather than appearing in `Task.tags`.
_RESERVED_TAGS = frozenset({
    "id", "due", "scheduled", "created", "completed", "blocked",
    "estimate", "actual", "effort",
})

_CHECKBOX_STATUS = {
    " ": TaskStatus.OPEN,
    "x": TaskStatus.CLOSED,
    "X": TaskStatus.CLOSED,
    "/": TaskStatus.IN_PROGRESS,
    "-": TaskStatus.CLOSED,
}

_CHECKBOX_FOR_STATUS = {
    TaskStatus.OPEN: " ",
    TaskStatus.CLOSED: "x",
    TaskStatus.IN_PROGRESS: "/",
    TaskStatus.BLOCKED: " ",
}

_TASK_RE = re.compile(r"^(\s*)- \[(.)\] (.+)$")

_known_emoji_alt = "|".join(re.escape(e) for e in EMOJI_TO_TAG)
_DATAVIEW_FULL_RE = re.compile(r"[(\[]\s*(\w[\w\s]*?)\s*::\s*(.*?)\s*[)\]]")
_HASHTAG_VAL_RE = re.compile(r"#([\w/-]+):(\S+)")
_HASHTAG_RE = re.compile(r"#([\w/-]+)")
_METADATA_START_RE = re.compile(
    rf"(?:^|(?<=\s))(?:(?P<emoji>{_known_emoji_alt})"
    rf"|(?P<hash>#[\w/-])"
    rf"|(?P<dataview>[(\[]\s*\w[\w\s]*?\s*::))",
)


# ---- Update operations -----------------------------------------------------


@dataclass(frozen=True)
class CreateTask:
    """Append a new task line to the appropriate taskfile."""


@dataclass(frozen=True)
class UpdateStatus:
    status: TaskStatus


@dataclass(frozen=True)
class UpdateText:
    text: str


@dataclass(frozen=True)
class UpdateDependencies:
    dependencies: Dependencies


@dataclass(frozen=True)
class UpdateMetadata:
    tags: Optional[List[str]] = None
    time_details: Optional[TimeBlock] = None


@dataclass(frozen=True)
class ArchiveTask:
    """Move a CLOSED task out of the active taskfile."""


Update = Union[
    CreateTask, UpdateStatus, UpdateText,
    UpdateDependencies, UpdateMetadata, ArchiveTask,
]


# ---- Parser ----------------------------------------------------------------


class TaskParser:
    def __init__(self, vault_root: Path):
        self.vault_root = Path(vault_root)
        self._efforts = EffortParser(self.vault_root)

    def scan(self) -> List[Path]:
        results: List[Path] = []
        root = self.vault_root / ROOT_TASKFILE
        if root.is_file():
            results.append(root)
        for effort in self._efforts.scan():
            tf = effort / ROOT_TASKFILE
            if tf.is_file():
                results.append(tf)
        return results

    def parse(self, file: Path) -> List[Task]:
        file = Path(file)
        if not file.is_file():
            return []

        lines = file.read_text(encoding="utf-8").splitlines()
        body_start = _skip_frontmatter(lines)

        effort_name = self._effort_for(file)
        last_updated = date.fromtimestamp(file.stat().st_mtime)

        records, wrote_back = self._collect_records(lines, body_start)
        if wrote_back:
            file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        notes_by_id = self._collect_notes(lines, body_start)

        children_of: Dict[str, List[str]] = {r.tags["id"]: [] for r in records}
        for rec in records:
            if rec.parent is not None:
                children_of[rec.parent.tags["id"]].append(rec.tags["id"])

        return [
            self._build_task(
                rec=rec,
                effort_name=effort_name,
                last_updated=last_updated,
                children=children_of[rec.tags["id"]],
                notes=notes_by_id.get(rec.tags["id"], []),
            )
            for rec in records
        ]

    def write(self, task: Task, update: Update) -> None:
        if isinstance(update, CreateTask):
            self._create(task)
            return
        if isinstance(update, UpdateStatus):
            self._mutate(task, status=update.status)
            return
        if isinstance(update, UpdateText):
            self._mutate(task, title=update.text)
            return
        if isinstance(update, UpdateDependencies):
            self._mutate(task, dependencies=update.dependencies)
            return
        if isinstance(update, UpdateMetadata):
            self._mutate(task, free_tags=update.tags, time_details=update.time_details)
            return
        if isinstance(update, ArchiveTask):
            self._archive(task)
            return
        raise TypeError(f"Unknown Update: {update!r}")

    # ---- parse helpers ----

    def _collect_records(
        self, lines: List[str], body_start: int,
    ) -> Tuple[List["_Record"], bool]:
        records: List[_Record] = []
        stack: List[_Record] = []
        section = ""
        wrote_back = False

        for i in range(body_start, len(lines)):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and not stripped.startswith("#["):
                hashes = len(stripped) - len(stripped.lstrip("#"))
                section = stripped[hashes:].strip()
                stack.clear()
                continue
            if not stripped.startswith("- [") or stripped.startswith("- [["):
                continue
            m = _TASK_RE.match(raw)
            if m is None:
                continue

            indent = _indent_level(m.group(1))
            checkbox = m.group(2)
            title, tags, dataview_tags = _split_tags(m.group(3))

            if not tags.get("id"):
                tags["id"] = generate_task_id()
                lines[i] = _build_line(indent, checkbox, title, tags, dataview_tags)
                wrote_back = True

            while stack and stack[-1].indent >= indent:
                stack.pop()
            parent = stack[-1] if stack else None

            rec = _Record(
                indent=indent,
                checkbox=checkbox,
                title=title,
                tags=tags,
                dataview_tags=dataview_tags,
                section=section,
                parent=parent,
            )
            records.append(rec)
            stack.append(rec)
        return records, wrote_back

    def _collect_notes(
        self, lines: List[str], body_start: int,
    ) -> Dict[str, List[str]]:
        notes: Dict[str, List[str]] = {}
        current_id: Optional[str] = None
        current_indent = -1
        for i in range(body_start, len(lines)):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and not stripped.startswith("#["):
                current_id = None
                continue
            m = _TASK_RE.match(raw)
            if m and not stripped.startswith("- [["):
                _t, tags, _dv = _split_tags(m.group(3))
                current_id = tags.get("id")
                current_indent = _indent_level(m.group(1))
                continue
            if current_id and stripped.startswith("-"):
                lead = raw[: len(raw) - len(raw.lstrip())]
                if _indent_level(lead) > current_indent:
                    body = stripped[1:].lstrip()
                    notes.setdefault(current_id, []).append(body)
                    continue
            current_id = None
        return notes

    def _build_task(
        self,
        *,
        rec: "_Record",
        effort_name: str,
        last_updated: date,
        children: List[str],
        notes: List[str],
    ) -> Task:
        tags = rec.tags
        blocked_value = tags.get("blocked", "")
        blocked = [b.strip() for b in blocked_value.split(",") if b.strip()]

        if blocked:
            status = TaskStatus.BLOCKED
        else:
            status = _CHECKBOX_STATUS.get(rec.checkbox, TaskStatus.OPEN)

        is_milestone = "milestone" in tags or "milestone" in rec.section.lower()

        free_tags = [
            f"{name}:{value}" if value else name
            for name, value in tags.items()
            if name not in _RESERVED_TAGS and not _is_emoji_key(name)
        ]

        time_details = TimeBlock(
            created=_coerce_date(tags.get("created", "")),
            last_updated=last_updated,
            due=_coerce_date(tags.get("due", "")),
            scheduled=_coerce_date(tags.get("scheduled", "")),
        )

        return Task(
            id=tags["id"],
            type=TaskType.MILESTONE if is_milestone else TaskType.TASK,
            status=status,
            text=rec.title,
            effort=effort_name,
            notes=notes,
            tags=free_tags,
            dependencies=Dependencies(
                blocked=blocked,
                parent=rec.parent.tags["id"] if rec.parent else "",
                children=children,
            ),
            time_details=time_details,
        )

    # ---- write helpers ----

    def _taskfile_for(self, effort: str) -> Path:
        if effort == "none":
            return self.vault_root / ROOT_TASKFILE
        active = self.vault_root / EFFORTS_DIR / effort / ROOT_TASKFILE
        if active.is_file():
            return active
        backlog = self.vault_root / EFFORTS_DIR / BACKLOG_DIR / effort / ROOT_TASKFILE
        if backlog.is_file():
            return backlog
        raise FileNotFoundError(f"No taskfile for effort {effort!r}")

    def _effort_for(self, file: Path) -> str:
        try:
            rel = file.relative_to(self.vault_root)
        except ValueError:
            return "none"
        parts = rel.parts
        if parts == (ROOT_TASKFILE,):
            return "none"
        if parts and parts[0] == EFFORTS_DIR and parts[-1] == ROOT_TASKFILE:
            if len(parts) == 4 and parts[1] == BACKLOG_DIR:
                return parts[2]
            if len(parts) == 3:
                return parts[1]
        return "none"

    def _create(self, task: Task) -> None:
        path = self._taskfile_for(task.effort)
        if not task.id:
            task.id = generate_task_id()

        tags: Dict[str, str] = {"id": task.id}
        td = task.time_details
        for fld in ("created", "due", "scheduled"):
            value = getattr(td, fld, None)
            if value and value != _NULL_DATE:
                tags[fld] = value.isoformat()
        if task.dependencies.blocked:
            tags["blocked"] = ",".join(task.dependencies.blocked)
        if task.type == TaskType.MILESTONE:
            tags.setdefault("milestone", "")
        for entry in task.tags:
            name, _, value = entry.partition(":")
            if name:
                tags[name] = value

        line = _build_line(
            indent_level=0,
            checkbox=_CHECKBOX_FOR_STATUS.get(task.status, " "),
            title=task.text,
            tags=tags,
            dataview_tags=set(),
        )
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + line + "\n", encoding="utf-8")

    def _mutate(
        self,
        task: Task,
        *,
        status: Optional[TaskStatus] = None,
        title: Optional[str] = None,
        dependencies: Optional[Dependencies] = None,
        free_tags: Optional[List[str]] = None,
        time_details: Optional[TimeBlock] = None,
    ) -> None:
        path = self._taskfile_for(task.effort)
        lines = path.read_text(encoding="utf-8").splitlines()
        idx = _find_task_line(lines, task.id)
        if idx is None:
            raise KeyError(f"Task {task.id!r} not found in {path}")

        m = _TASK_RE.match(lines[idx])
        indent = _indent_level(m.group(1))
        checkbox = m.group(2)
        existing_title, tags, dataview_tags = _split_tags(m.group(3))

        if status is not None:
            checkbox = _CHECKBOX_FOR_STATUS.get(status, checkbox)
        new_title = title if title is not None else existing_title

        if dependencies is not None:
            if dependencies.blocked:
                tags["blocked"] = ",".join(dependencies.blocked)
            else:
                tags.pop("blocked", None)

        if time_details is not None:
            for fld in ("created", "due", "scheduled"):
                value = getattr(time_details, fld, None)
                if value and value != _NULL_DATE:
                    tags[fld] = value.isoformat()
                else:
                    tags.pop(fld, None)

        if free_tags is not None:
            for k in [
                k for k in tags
                if k not in _RESERVED_TAGS and not _is_emoji_key(k)
            ]:
                tags.pop(k)
                dataview_tags.discard(k)
            for entry in free_tags:
                name, _, value = entry.partition(":")
                if name:
                    tags[name] = value

        lines[idx] = _build_line(indent, checkbox, new_title, tags, dataview_tags)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _archive(self, task: Task) -> None:
        path = self._taskfile_for(task.effort)
        lines = path.read_text(encoding="utf-8").splitlines()
        idx = _find_task_line(lines, task.id)
        if idx is None:
            return
        m = _TASK_RE.match(lines[idx])
        task_indent = _indent_level(m.group(1)) if m else 0
        end = idx + 1
        while end < len(lines):
            stripped = lines[end].strip()
            if not stripped:
                end += 1
                continue
            if stripped.startswith("#"):
                break
            if stripped.startswith("- [") and not stripped.startswith("- [["):
                break
            lead = lines[end][: len(lines[end]) - len(lines[end].lstrip())]
            if _indent_level(lead) <= task_indent:
                break
            end += 1
        del lines[idx:end]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- record / private helpers ----------------------------------------------


@dataclass
class _Record:
    indent: int
    checkbox: str
    title: str
    tags: Dict[str, str]
    dataview_tags: Set[str]
    section: str
    parent: Optional["_Record"]


def _indent_level(indent: str) -> int:
    return len(indent.replace("\t", "    ")) // 4


def _coerce_date(value: str) -> date:
    if not value:
        return _NULL_DATE
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return _NULL_DATE


def _is_emoji_key(name: str) -> bool:
    return any(emoji.is_emoji(c) for c in name)


def _skip_frontmatter(lines: List[str]) -> int:
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return 0
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            return j + 1
    return 0


def _build_line(
    indent_level: int,
    checkbox: str,
    title: str,
    tags: Dict[str, str],
    dataview_tags: Set[str],
) -> str:
    indent = "    " * indent_level
    tag_str = render_tags(tags, dataview_tags)
    if tag_str:
        return f"{indent}- [{checkbox}] {title} {tag_str}"
    return f"{indent}- [{checkbox}] {title}"


def _find_task_line(lines: List[str], task_id: str) -> Optional[int]:
    for i, raw in enumerate(lines):
        if raw.lstrip().startswith("- [["):
            continue
        m = _TASK_RE.match(raw)
        if m is None:
            continue
        _t, tags, _dv = _split_tags(m.group(3))
        if tags.get("id") == task_id:
            return i
    return None


# ---- tag tail parsing (mirrors src/parsers/task_parser.py) -----------------


def _bracket_depth_at(text: str, pos: int) -> int:
    depth = 0
    for ch in text[:pos]:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
    return depth


def _find_metadata_start(text: str) -> Optional[int]:
    for m in _METADATA_START_RE.finditer(text):
        if m.group("hash"):
            if _bracket_depth_at(text, m.start()) == 0:
                return m.start()
            continue
        return m.start()
    return None


def _is_metadata_token(tok: str) -> bool:
    if tok in EMOJI_TO_TAG:
        return True
    if emoji.is_emoji(tok):
        return True
    if tok.startswith("#"):
        return True
    if tok and tok[0] in "([" and (len(tok) < 2 or tok[1] != "["):
        return True
    return False


def _parse_metadata(tail: str) -> Tuple[Dict[str, str], Set[str]]:
    tokens = tail.split()
    tags: Dict[str, str] = {}
    dataview: Set[str] = set()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in EMOJI_TO_TAG:
            tags[EMOJI_TO_TAG[tok]] = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
            continue
        if tok and tok[0] in "([" and (len(tok) < 2 or tok[1] != "["):
            closer = ")" if tok[0] == "(" else "]"
            parts = [tok]
            j = i + 1
            while j < len(tokens) and closer not in parts[-1]:
                parts.append(tokens[j])
                j += 1
            dv = _DATAVIEW_FULL_RE.fullmatch(" ".join(parts))
            if dv:
                tags[dv.group(1)] = dv.group(2)
                dataview.add(dv.group(1))
                i = j
                continue
        if tok.startswith("#"):
            mv = _HASHTAG_VAL_RE.fullmatch(tok)
            if mv:
                tags[mv.group(1)] = mv.group(2)
                i += 1
                continue
            mh = _HASHTAG_RE.fullmatch(tok)
            if mh:
                tags[mh.group(1)] = ""
                i += 1
                continue
        if emoji.is_emoji(tok):
            i += 1
            val: List[str] = []
            while i < len(tokens) and not _is_metadata_token(tokens[i]):
                val.append(tokens[i])
                i += 1
            tags[tok] = " ".join(val)
            continue
        i += 1
    return tags, dataview


def _split_tags(text: str) -> Tuple[str, Dict[str, str], Set[str]]:
    pos = _find_metadata_start(text)
    if pos is None:
        return text.strip(), {}, set()
    tags, dv = _parse_metadata(text[pos:])
    return text[:pos].strip(), tags, dv
