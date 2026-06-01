"""
Task parser.

Implements the parser surface from `specs/arch/parser.md` for the tasks
system (`specs/systems/tasks/readme.md`).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import emoji

from schemas.tasks import Dependencies, Note, Task, TaskStatus, TaskType
from schemas.time import TimeBlock
from utils.formatting import EMOJI_TO_TAG, render_tags
from utils.ids import generate_task_id
from vault.parser import Parser
from vault.efforts.parser import BACKLOG_DIR, EFFORTS_DIR
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


# Field names tracked for the per-task dirty-field merge during flush.
_FIELD_TEXT = "text"
_FIELD_STATUS = "status"
_FIELD_DEPENDENCIES = "dependencies"
_FIELD_TAGS = "tags"
_FIELD_TIME = "time_details"


# ---- Parser ----------------------------------------------------------------


TaskParserInterface = Parser[Task, Update]
class TaskParser:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self._db: Any = None
        self._watcher: Any = None
        self._taskfile_handles: Dict[Path, WatcherHandle] = {}
        self._dirty_fields: Dict[str, Set[str]] = {}
        self._file_for_task: Dict[str, Path] = {}

    # ---- initialize ----

    def initialize(self, db: Any, watcher: Any) -> None:
        self._db = db
        self._watcher = watcher
        # Global taskfile (no owning effort).
        root = self.vault_root / ROOT_TASKFILE
        self.register_taskfile(root)

    def register_taskfile(self, taskfile: Path) -> None:
        events = frozenset({
            EventType.CREATE, EventType.MODIFY, EventType.DELETE,
            EventType.FLUSH,
        })
        handle = self._watcher.register(
            WatchCriterion(target=taskfile, events=events),
            self._on_taskfile_event,
        )
        log.info('[TASKS] Registering watcher for file=%s', taskfile)
        self._taskfile_handles[taskfile] = handle

    def taskfile_handles_under(
        self, folder: Path,
    ) -> List[Tuple[Path, WatcherHandle]]:
        """Return (taskfile, handle) pairs for every taskfile under `folder`."""
        try:
            folder_resolved = folder.resolve()
        except OSError:
            folder_resolved = folder
        out: List[Tuple[Path, WatcherHandle]] = []
        for tf, handle in self._taskfile_handles.items():
            try:
                tf.resolve().relative_to(folder_resolved)
            except (ValueError, OSError):
                continue
            out.append((tf, handle))
        return out

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
                self._db.delete(task)
                self._dirty_fields.pop(task.id, None)
                self._file_for_task.pop(task.id, None)
            return
        if event == EventType.FLUSH:
            self._flush(file)
            return
        if file.is_file():
            self._reparse_and_seed(file)
        self.prune_dangling_refs()

    def _reparse_and_seed(self, file: Path) -> None:
        parsed = self.parse(file)
        parsed_ids = {t.id for t in parsed}
        for task in self._elements_for_file(file):
            if task.id not in parsed_ids:
                self._db.delete(task)
                self._dirty_fields.pop(task.id, None)
                self._file_for_task.pop(task.id, None)
        for task in parsed:
            self._db.update(task)
            self._file_for_task[task.id] = file

    def prune_dangling_refs(self) -> None:
        """Drop blocked / parent / child references to ids no longer in the table."""
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
            self._db.update(task)

    def parse(self, file: Path) -> List[Task]:
        file = Path(file)
        if not file.is_file():
            return []

        lines = file.read_text(encoding="utf-8").splitlines()
        body_start, frontmatter_lines = _read_frontmatter(lines)

        effort_name = self._effort_for(file)
        last_updated = date.fromtimestamp(file.stat().st_mtime)

        try:
            rel_path = file.relative_to(self.vault_root).as_posix()
        except ValueError:
            rel_path = str(file)
        records = self._collect_records(lines, body_start, rel_path)
        notes_by_id = self._collect_notes(lines, body_start)

        children_of: Dict[str, List[str]] = {r.tags["id"]: [] for r in records}
        for rec in records:
            if rec.parent is not None:
                children_of[rec.parent.tags["id"]].append(rec.tags["id"])

        out: List[Task] = [
            _taskfile_row(
                file=file,
                vault_root=self.vault_root,
                effort_name=effort_name,
                frontmatter_lines=frontmatter_lines,
                last_updated=last_updated,
            ),
        ]
        out.extend(
            self._build_task(
                rec=rec,
                effort_name=effort_name,
                last_updated=last_updated,
                children=children_of[rec.tags["id"]],
                notes=notes_by_id.get(rec.tags["id"], []),
            )
            for rec in records
        )
        return out

    def update(self, task: Task, op: Update) -> None:
        if isinstance(op, CreateTask):
            if not task.id:
                task.id = generate_task_id()
            self._db.update(task)
            self._mark_task_dirty(task, {
                _FIELD_TEXT, _FIELD_STATUS, _FIELD_DEPENDENCIES,
                _FIELD_TAGS, _FIELD_TIME,
            })
            return
        if isinstance(op, ArchiveTask):
            self._db.delete(task)
            self._dirty_fields.pop(task.id, None)
            file = self._file_for_task.pop(task.id, None) or self._resolve_file(task)
            if file is not None and active_origin() is None:
                self._watcher.mark_dirty(file)
            return
        touched: Set[str] = set()
        if isinstance(op, UpdateStatus):
            task.status = op.status
            touched.add(_FIELD_STATUS)
            if op.status == TaskStatus.CLOSED:
                if task.time_details.completed is None:
                    task.time_details.completed = date.today()
                    touched.add(_FIELD_TIME)
            elif task.time_details.completed is not None:
                task.time_details.completed = None
                touched.add(_FIELD_TIME)
        elif isinstance(op, UpdateText):
            task.text = op.text
            touched.add(_FIELD_TEXT)
        elif isinstance(op, UpdateDependencies):
            task.dependencies = op.dependencies
            if op.dependencies.blocked:
                task.status = TaskStatus.BLOCKED
            touched.add(_FIELD_DEPENDENCIES)
            touched.add(_FIELD_STATUS)
        elif isinstance(op, UpdateMetadata):
            if op.tags is not None:
                task.tags = list(op.tags)
                touched.add(_FIELD_TAGS)
            if op.time_details is not None:
                task.time_details = op.time_details
                touched.add(_FIELD_TIME)
        else:
            raise TypeError(f"Unknown Update: {op!r}")
        self._db.update(task)
        self._mark_task_dirty(task, touched)

    def _mark_task_dirty(self, task: Task, fields: Set[str]) -> None:
        if active_origin() is not None:
            # Inbound (parse-driven) write; the file is authoritative.
            return
        if not fields:
            return
        self._dirty_fields.setdefault(task.id, set()).update(fields)
        file = self._file_for_task.get(task.id) or self._resolve_file(task)
        if file is None:
            return
        self._file_for_task[task.id] = file
        self._watcher.mark_dirty(file)

    def _resolve_file(self, task: Task) -> Optional[Path]:
        if task.effort == "none":
            return self.vault_root / ROOT_TASKFILE
        active = self.vault_root / EFFORTS_DIR / task.effort / ROOT_TASKFILE
        if active.is_file():
            return active
        backlog = (
            self.vault_root / EFFORTS_DIR / BACKLOG_DIR
            / task.effort / ROOT_TASKFILE
        )
        if backlog.is_file():
            return backlog
        return None

    # ---- flush ----

    def flush_file(self, file: Path) -> None:
        """Synchronously flush `file`. Used at shutdown / before folder moves."""
        self._flush(file)

    def _flush(self, file: Path) -> None:
        if not file.is_file():
            # File was deleted out from under us; nothing to project.
            return

        on_disk = {t.id: t for t in self.parse(file)}
        db_tasks = {t.id: t for t in self._elements_for_file(file)}

        merged: Dict[str, Task] = {}
        for tid, db_task in db_tasks.items():
            parsed = on_disk.get(tid)
            if parsed is None:
                # Created in DB but not yet on disk — emit as-is.
                merged[tid] = db_task
                continue
            dirty = self._dirty_fields.get(tid, set())
            merged[tid] = _merge_task(parsed, db_task, dirty)

        # Fold tasks present on disk but absent from DB back into the DB.
        for tid, parsed in on_disk.items():
            if tid not in merged:
                merged[tid] = parsed
                self._db.update(parsed)

        taskfile_row = merged.get(_taskfile_id(file, self.vault_root))
        tasks = [t for t in merged.values() if t.type != TaskType.TASKFILE]
        content = _render_file(taskfile_row, tasks)

        self._watcher.mark_self_write(file)
        file.write_text(content, encoding="utf-8")

        for tid in merged:
            self._dirty_fields.pop(tid, None)
            self._file_for_task[tid] = file

    # ---- parse helpers ----

    def _collect_records(
        self, lines: List[str], body_start: int, rel_path: str,
    ) -> List["_Record"]:
        records: List[_Record] = []
        stack: List[_Record] = []
        section = ""
        current_milestone: Optional[_Record] = None

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
                        tags["id"] = _stable_id(rel_path, i, title)
                    rec = _Record(
                        indent=-1,
                        checkbox="",
                        title=title,
                        tags=tags,
                        dataview_tags=dataview_tags,
                        section=section,
                        parent=None,
                        type=TaskType.MILESTONE,
                        line_index=i,
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
                tags["id"] = _stable_id(rel_path, i, title)

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
                line_index=i,
            )
            records.append(rec)
            stack.append(rec)
        return records

    def _collect_notes(
        self, lines: List[str], body_start: int,
    ) -> Dict[str, List[Note]]:
        notes: Dict[str, List[Note]] = {}
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
                note_indent = _indent_level(lead)
                if note_indent > current_indent:
                    body = stripped[1:].lstrip()
                    relative = max(0, note_indent - current_indent - 1)
                    notes.setdefault(current_id, []).append(
                        Note(indent=relative, text=body),
                    )
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
        notes: List[Note],
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
            file_order=rec.line_index,
            estimate=tags.get("estimate", ""),
            actual=tags.get("actual", ""),
            notes=notes,
            tags=free_tags,
            dependencies=Dependencies(
                blocked=blocked,
                parent=rec.parent.tags["id"] if rec.parent else "",
                children=children,
            ),
            time_details=time_details,
        )

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


# ---- TASKFILE row ----------------------------------------------------------


def _taskfile_id(file: Path, vault_root: Path) -> str:
    try:
        rel = file.relative_to(vault_root).as_posix()
    except ValueError:
        rel = str(file)
    return "tf_" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:14]


def _taskfile_row(
    *,
    file: Path,
    vault_root: Path,
    effort_name: str,
    frontmatter_lines: List[str],
    last_updated: date,
) -> Task:
    try:
        rel = file.relative_to(vault_root).as_posix()
    except ValueError:
        rel = str(file)
    notes = [
        Note(indent=0, text=line)
        for line in frontmatter_lines
        if line.strip()
    ]
    return Task(
        id=_taskfile_id(file, vault_root),
        type=TaskType.TASKFILE,
        status=TaskStatus.OPEN,
        text=rel,
        effort=effort_name,
        file_order=0,
        notes=notes,
        tags=[],
        dependencies=Dependencies(blocked=[], parent="", children=[]),
        time_details=TimeBlock(last_updated=last_updated),
    )


# ---- field-level merge -----------------------------------------------------


def _merge_task(parsed: Task, db: Task, dirty_fields: Set[str]) -> Task:
    """DB wins for dirty fields; the parsed (on-disk) value wins otherwise."""
    out = parsed.model_copy(deep=True)
    if _FIELD_STATUS in dirty_fields:
        out.status = db.status
    if _FIELD_TEXT in dirty_fields:
        out.text = db.text
    if _FIELD_DEPENDENCIES in dirty_fields:
        out.dependencies = db.dependencies
    if _FIELD_TAGS in dirty_fields:
        out.tags = list(db.tags)
    if _FIELD_TIME in dirty_fields:
        out.time_details = db.time_details
    return out


# ---- formatting helpers ----------------------------------------------------


def _build_meta_tags(task: Task) -> Dict[str, str]:
    tags: Dict[str, str] = {"id": task.id}
    td = task.time_details
    for fld in ("created", "due", "scheduled", "completed"):
        value = getattr(td, fld, None)
        if value is not None:
            tags[fld] = value.isoformat()
    if task.dependencies.blocked:
        tags["blocked"] = ",".join(task.dependencies.blocked)
    if task.estimate:
        tags["estimate"] = task.estimate
    if task.actual:
        tags["actual"] = task.actual
    for entry in task.tags:
        name, _, value = entry.partition(":")
        if name:
            tags[name] = value
    return tags


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


def _build_milestone_heading(
    title: str, tags: Dict[str, str], dataview_tags: Set[str],
) -> str:
    tag_str = render_tags(tags, dataview_tags)
    if tag_str:
        return f"#### {title} {tag_str}"
    return f"#### {title}"


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


def _depth_of(task: Task, by_id: Dict[str, Task]) -> int:
    depth = 0
    parent_id = task.dependencies.parent
    while parent_id:
        parent = by_id.get(parent_id)
        if parent is None or parent.type == TaskType.MILESTONE:
            break
        depth += 1
        parent_id = parent.dependencies.parent
    return depth


def _render_file(taskfile: Optional[Task], tasks: List[Task]) -> str:
    by_id = {t.id: t for t in tasks}
    ordered = _order_tasks(tasks)

    out: List[str] = []
    if taskfile is not None and taskfile.notes:
        out.append("---")
        for note in taskfile.notes:
            out.append(note.text)
        out.append("---")
        out.append("")

    for task in ordered:
        if task.type == TaskType.MILESTONE:
            out.append(_render_milestone_line(task))
            continue
        depth = _depth_of(task, by_id)
        out.append(_render_task_line(task, depth))
        for note in task.notes:
            file_indent = "    " * (depth + 1 + note.indent)
            out.append(f"{file_indent}- {note.text}")

    return "\n".join(out) + ("\n" if out else "")


def _order_tasks(tasks: List[Task]) -> List[Task]:
    """Sort tasks for emission, preserving original order where known."""
    by_parent: Dict[str, List[Task]] = {}
    by_id = {t.id: t for t in tasks}
    for t in tasks:
        by_parent.setdefault(t.dependencies.parent, []).append(t)

    def emit_children(parent_id: str) -> List[Task]:
        siblings = by_parent.get(parent_id, [])
        existing = sorted(
            (s for s in siblings if s.file_order >= 0),
            key=lambda s: s.file_order,
        )
        new = [s for s in siblings if s.file_order < 0]
        out: List[Task] = []
        for sib in existing + new:
            out.append(sib)
            out.extend(emit_children(sib.id))
        return out

    roots = [
        t for t in tasks
        if not t.dependencies.parent or t.dependencies.parent not in by_id
    ]
    roots_existing = sorted(
        (r for r in roots if r.file_order >= 0), key=lambda r: r.file_order,
    )
    roots_new = [r for r in roots if r.file_order < 0]
    out: List[Task] = []
    for root in roots_existing + roots_new:
        out.append(root)
        out.extend(emit_children(root.id))
    return out


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
    line_index: int = -1


def _stable_id(rel_path: str, line_index: int, title: str) -> str:
    """Deterministic id for an id-less line, stable across re-parses.

    Using the file path, line position, and title keeps the seed parse and
    the flush-time re-parse in agreement, so a generated id is reconciled
    rather than duplicated when the line is written back.
    """
    digest = hashlib.sha1(
        f"{rel_path}\x00{line_index}\x00{title}".encode("utf-8")
    )
    return digest.hexdigest()[:6]


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


def _read_frontmatter(lines: List[str]) -> Tuple[int, List[str]]:
    """Return (body_start_index, frontmatter_body_lines)."""
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return 0, []
    for j in range(i + 1, len(lines)):
        if lines[j].strip() == "---":
            return j + 1, list(lines[i + 1 : j])
    return 0, []


def _skip_frontmatter(lines: List[str]) -> int:
    body_start, _ = _read_frontmatter(lines)
    return body_start


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
