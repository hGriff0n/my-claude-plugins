"""
Task parser.

Implements the parser surface from `specs/arch/parser.md` for the tasks
system (`specs/systems/tasks/readme.md`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import emoji

from schemas.tasks import Dependencies, Task, TaskStatus, TaskType
from schemas.time import TimeBlock
from utils.formatting import EMOJI_TO_TAG, render_tags
from utils.ids import generate_task_id
from vault.parser import Parser
from vault.efforts.parser import BACKLOG_DIR, EFFORTS_DIR, EffortParser
from vault.watcher import EventType, WatchCriterion, WatcherHandle, active_origin

log = logging.getLogger(__name__)

SYSTEM_NAME = "tasks"
ROOT_TASKFILE = "01 TASKS.md"

# Tags that carry model-field semantics rather than appearing in `Task.tags`.
_RESERVED_TAGS = frozenset({
    "id", "due", "scheduled", "created", "completed", "blocked",
    "estimate", "actual", "effort", "milestone",
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
_MILESTONE_HEADING_RE = re.compile(r"^####(?!#)\s+(.+)$")

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


TaskParserInterface = Parser[Task, Update]
class TaskParser:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self._db: Any = None
        self._watcher: Any = None
        self._debouncer: Any = None
        self._taskfile_handles: Dict[Path, WatcherHandle] = {}

    # ---- initialize ----

    def initialize(self, db: Any, watcher: Any, debouncer: Any) -> None:
        self._db = db
        self._watcher = watcher
        self._debouncer = debouncer
        debouncer.register_system(
            name=SYSTEM_NAME,
            lag=timedelta(milliseconds=500),
            parent_file_resolver=self._parent_file,
            writer=self.write,
            elements_for_file=self._elements_for_file,
            models={Task.__name__: Task},
        )
        # Global taskfile (no owning effort).
        root = self.vault_root / ROOT_TASKFILE
        self.register_taskfile(root)

    def register_taskfile(self, taskfile: Path) -> None:
        events = frozenset({EventType.CREATE, EventType.MODIFY, EventType.DELETE})
        handle = self._watcher.register(
            WatchCriterion(target=taskfile, events=events),
            self._on_taskfile_event,
        )
        logging.info(f'[TASKS] Registering watcher for file={taskfile}')
        self._taskfile_handles[taskfile] = handle

    def _parent_file(self, task: Task) -> Path:
        # Resolver returns the canonical path regardless of whether the file
        # currently exists on disk; debouncer creates it if needed.
        if task.effort == "none":
            return self.vault_root / ROOT_TASKFILE
        backlog = self.vault_root / EFFORTS_DIR / BACKLOG_DIR / task.effort / ROOT_TASKFILE
        if backlog.is_file():
            return backlog
        return self.vault_root / EFFORTS_DIR / task.effort / ROOT_TASKFILE

    def _elements_for_file(self, file: Path) -> List[Task]:
        try:
            rel = file.relative_to(self.vault_root)
        except ValueError:
            return []
        if rel.parts == (ROOT_TASKFILE,):
            effort_name = "none"
        elif (
            rel.parts and rel.parts[0] == EFFORTS_DIR
            and rel.parts[-1] == ROOT_TASKFILE
        ):
            if len(rel.parts) == 4 and rel.parts[1] == BACKLOG_DIR:
                effort_name = rel.parts[2]
            elif len(rel.parts) == 3:
                effort_name = rel.parts[1]
            else:
                return []
        else:
            return []
        return [
            t for t in self._db.query('SELECT * FROM "task"')
            if t.effort == effort_name
        ]

    def _on_taskfile_event(
        self, file: Path, event: EventType, handle: WatcherHandle,
    ) -> None:
        if event == EventType.DELETE:
            for task in self._elements_for_file(file):
                self._db.delete(task, origin=handle)
        elif file.is_file():
            for task in self.parse(file):
                self._db.update(task, origin=handle)
        self.prune_dangling_refs(origin=handle)

    def prune_dangling_refs(self, *, origin: Any = None) -> None:
        """Drop blocked / parent / child references to ids no longer in the table.

        Runs after every parse cycle (initial seed and watcher-driven
        re-parses) so the index converges to a state where every reference
        resolves to a live task. The corresponding `blocked` tag is
        rewritten on disk via the standard write path.
        """
        tasks = self._db.query('SELECT * FROM "task"')
        valid_ids = {t.id for t in tasks}
        for task in tasks:
            deps = task.dependencies
            new_blocked = [b for b in deps.blocked if b in valid_ids]
            new_parent = deps.parent if deps.parent in valid_ids else ""
            new_children = [c for c in deps.children if c in valid_ids]
            if (
                new_blocked == deps.blocked
                and new_parent == deps.parent
                and new_children == deps.children
            ):
                continue
            task.dependencies = Dependencies(
                blocked=new_blocked, parent=new_parent, children=new_children,
            )
            if task.status == TaskStatus.BLOCKED and not new_blocked:
                task.status = TaskStatus.OPEN
            self._db.update(task, origin=origin)

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

    def update(self, task: Task, op: Update) -> None:
        origin = active_origin()
        if isinstance(op, CreateTask):
            if not task.id:
                task.id = generate_task_id()
            self._db.update(task, origin=origin)
            return
        if isinstance(op, ArchiveTask):
            self._db.delete(task, origin=origin)
            return
        if isinstance(op, UpdateStatus):
            task.status = op.status
        elif isinstance(op, UpdateText):
            task.text = op.text
        elif isinstance(op, UpdateDependencies):
            task.dependencies = op.dependencies
            if op.dependencies.blocked:
                task.status = TaskStatus.BLOCKED
        elif isinstance(op, UpdateMetadata):
            if op.tags is not None:
                task.tags = list(op.tags)
            if op.time_details is not None:
                task.time_details = op.time_details
        else:
            raise TypeError(f"Unknown Update: {op!r}")
        self._db.update(task, origin=origin)

    def write(self, file: Path, elements: List[Task]) -> None:
        """Project tasks to disk by rewriting the taskfile body.

        Builds an ephemeral TASKFILE wrapper from `file`'s frontmatter and
        the parentless `elements` to drive a uniform recursive emit.
        Frontmatter is read from disk because TASKFILE tasks aren't
        persisted in the DB.
        """
        if not elements and not file.exists():
            return
        file.parent.mkdir(parents=True, exist_ok=True)

        frontmatter_notes = (
            _frontmatter_to_notes(file) if file.is_file() else []
        )

        by_id = {t.id: t for t in elements}
        children_by_parent: Dict[str, List[Task]] = {}
        roots: List[Task] = []
        for task in elements:
            parent = task.dependencies.parent
            if parent and parent in by_id:
                children_by_parent.setdefault(parent, []).append(task)
            else:
                roots.append(task)

        lines: List[str] = []

        def emit(task: Task, depth: int) -> None:
            if task.type == TaskType.MILESTONE:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(_render_milestone_line(task))
                lines.append("")
                for child in children_by_parent.get(task.id, []):
                    emit(child, 0)
                return
            lines.append(_render_task_line(task, depth))
            for note in task.notes:
                lines.append("    " * (depth + 1) + "- " + note)
            for child in children_by_parent.get(task.id, []):
                emit(child, depth + 1)

        if frontmatter_notes:
            lines.append("---")
            lines.extend(frontmatter_notes)
            lines.append("---")
            lines.append("")

        for task in roots:
            emit(task, 0)

        file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- parse helpers ----

    def _collect_records(
        self, lines: List[str], body_start: int,
    ) -> Tuple[List["_Record"], bool]:
        records: List[_Record] = []
        stack: List[_Record] = []
        section = ""
        current_milestone: Optional[_Record] = None
        wrote_back = False

        for i in range(body_start, len(lines)):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#") and not stripped.startswith("#["):
                ms = _MILESTONE_HEADING_RE.match(stripped)
                if ms:
                    title, tags, dataview_tags = _split_tags(ms.group(1))
                    if not tags.get("id"):
                        tags["id"] = generate_task_id()
                        lines[i] = _build_milestone_heading(
                            title, tags, dataview_tags,
                        )
                        wrote_back = True
                    rec = _Record(
                        indent=-1,
                        checkbox="",
                        title=title,
                        tags=tags,
                        dataview_tags=dataview_tags,
                        section=section,
                        parent=None,
                        type=TaskType.MILESTONE,
                    )
                    records.append(rec)
                    current_milestone = rec
                    stack.clear()
                    continue
                hashes = len(stripped) - len(stripped.lstrip("#"))
                section = stripped[hashes:].strip()
                stack.clear()
                current_milestone = None
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
            if stack:
                parent = stack[-1]
            elif indent == 0 and current_milestone is not None:
                parent = current_milestone
            else:
                parent = None

            is_milestone_tag = "milestone" in tags or "milestone" in section.lower()
            rec = _Record(
                indent=indent,
                checkbox=checkbox,
                title=title,
                tags=tags,
                dataview_tags=dataview_tags,
                section=section,
                parent=parent,
                type=TaskType.MILESTONE if is_milestone_tag else TaskType.TASK,
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

        if rec.type == TaskType.MILESTONE:
            status = TaskStatus.OPEN
        elif blocked:
            status = TaskStatus.BLOCKED
        else:
            status = _CHECKBOX_STATUS.get(rec.checkbox, TaskStatus.OPEN)

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
            completed=_coerce_date(tags.get("completed", "")),
        )

        return Task(
            id=tags["id"],
            type=rec.type,
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


def _build_meta_tags(task: Task) -> Dict[str, str]:
    tags: Dict[str, str] = {"id": task.id}
    td = task.time_details
    for fld in ("created", "due", "scheduled", "completed"):
        value = getattr(td, fld, None)
        if value is not None:
            tags[fld] = value.isoformat()
    if task.dependencies.blocked:
        tags["blocked"] = ",".join(task.dependencies.blocked)
    for entry in task.tags:
        name, _, value = entry.partition(":")
        if name:
            tags[name] = value
    return tags


def _render_task_line(task: Task, depth: int) -> str:
    return _build_line(
        indent_level=depth,
        checkbox=_CHECKBOX_FOR_STATUS.get(task.status, " "),
        title=task.text,
        tags=_build_meta_tags(task),
        dataview_tags=set(),
    )


def _render_milestone_line(task: Task) -> str:
    return _build_milestone_heading(
        task.text, _build_meta_tags(task), set(),
    )


def _build_milestone_heading(
    title: str, tags: Dict[str, str], dataview_tags: Set[str],
) -> str:
    tag_str = render_tags(tags, dataview_tags)
    if tag_str:
        return f"#### {title} {tag_str}"
    return f"#### {title}"


def _frontmatter_to_notes(file: Path) -> List[str]:
    fm = _read_frontmatter(file)
    if not fm:
        return []
    fm_lines = fm.splitlines()
    inner: List[str] = []
    started = False
    for line in fm_lines:
        if line.strip() == "---":
            if not started:
                started = True
                continue
            break
        if started:
            inner.append(line)
    return [ln for ln in inner if ln.strip()]


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
    type: TaskType = TaskType.TASK


def _indent_level(indent: str) -> int:
    return len(indent.replace("\t", "    ")) // 4


def _coerce_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _is_emoji_key(name: str) -> bool:
    return any(emoji.is_emoji(c) for c in name)


def _read_frontmatter(file: Path) -> str:
    """Return the leading `--- ... ---` block verbatim, or empty string."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return ""
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            return "\n".join(lines[: j + 1])
    return ""


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
