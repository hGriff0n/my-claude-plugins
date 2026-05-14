"""POST /tasks/archive — bulk-archive CLOSED tasks to daily notes."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.tasks import Task, TaskStatus, TaskType
from utils.obsidian import (
    CONTENT_CHUNK_BYTES,
    obsidian_cli,
    split_on_line_boundaries,
)
from vault.tasks.parser import (
    ArchiveTask,
    UpdateDependencies,
    UpdateStatus,
)

router = APIRouter()
log = logging.getLogger(__name__)


class TaskUpdateAction(str, Enum):
    OPENED = "OPENED"
    CLOSED = "CLOSED"


class TaskUpdateRecord(BaseModel):
    id: str
    action: TaskUpdateAction


class ArchiveTasksRequest(BaseModel):
    ids: Optional[List[str]] = None
    effort: Optional[str] = None
    dry_run: bool = False


class ArchiveTasksResponse(BaseModel):
    archived: Dict[str, int]
    failures: List[str]
    updates: List[TaskUpdateRecord]
    dry_run: bool


def _completed_date(task: Task) -> str:
    completed = task.time_details.completed
    if completed is None:
        return ""
    return completed.isoformat()


def _select_tasks(
    app: App, req: ArchiveTasksRequest,
) -> List[Task]:
    all_tasks = app.db.query('SELECT * FROM "task"')
    if req.ids is not None:
        by_id = {t.id: t for t in all_tasks}
        selected: List[Task] = []
        for tid in req.ids:
            task = by_id.get(tid)
            if task is None:
                raise HTTPException(
                    status_code=400, detail=f"Task '{tid}' not found"
                )
            if task.status != TaskStatus.CLOSED:
                raise HTTPException(
                    status_code=400, detail=f"Task '{tid}' is not CLOSED"
                )
            selected.append(task)
        return selected
    closed = [t for t in all_tasks if t.status == TaskStatus.CLOSED]
    if req.effort is not None:
        closed = [t for t in closed if t.effort == req.effort]
    return closed


def _has_open_descendants(
    task: Task, by_id: Dict[str, Task], all_closed_ids: Set[str],
) -> bool:
    for child_id in task.dependencies.children:
        child = by_id.get(child_id)
        if child is None:
            continue
        if child.status != TaskStatus.CLOSED:
            return True
        if _has_open_descendants(child, by_id, all_closed_ids):
            return True
    return False


def _open_child_ids(task: Task, by_id: Dict[str, Task]) -> List[str]:
    return [
        cid for cid in task.dependencies.children
        if (c := by_id.get(cid)) is not None and c.status != TaskStatus.CLOSED
    ]


def _integrity_reopen(
    app: App, candidates: List[Task], dry_run: bool,
) -> tuple[List[Task], List[str]]:
    """Filter candidates, reopening parents that still have open descendants."""
    all_tasks = app.db.query('SELECT * FROM "task"')
    by_id = {t.id: t for t in all_tasks}
    closed_ids = {t.id for t in all_tasks if t.status == TaskStatus.CLOSED}

    keep: List[Task] = []
    reopened: List[str] = []
    for task in candidates:
        if _has_open_descendants(task, by_id, closed_ids):
            reopened.append(task.id)
            if not dry_run:
                open_kids = _open_child_ids(task, by_id)
                app.task_parser.update(task, UpdateStatus(status=TaskStatus.OPEN))
                from schemas.tasks import Dependencies
                new_deps = Dependencies(
                    blocked=open_kids,
                    parent=task.dependencies.parent,
                    children=task.dependencies.children,
                )
                app.task_parser.update(task, UpdateDependencies(dependencies=new_deps))
            continue
        keep.append(task)
    return keep, reopened


def _group_by_date(tasks: List[Task]) -> Dict[str, List[Task]]:
    groups: Dict[str, List[Task]] = defaultdict(list)
    for task in tasks:
        d = _completed_date(task)
        if d:
            groups[d].append(task)
    return dict(groups)


def _daily_note_path(date_str: str) -> Path:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (
        Path("areas") / "journal" / dt.strftime("%Y")
        / dt.strftime("%m %B") / f"{dt.strftime('%d')}.md"
    )


def _render_archive_block(
    tasks_on_date: List[Task], all_archive_ids: Set[str],
) -> str:
    """Render tasks for a single date, nesting under same-date parents only."""
    on_date_ids = {t.id for t in tasks_on_date}
    by_id = {t.id: t for t in tasks_on_date}
    children_of: Dict[str, List[Task]] = defaultdict(list)
    roots: List[Task] = []
    for t in tasks_on_date:
        pid = t.dependencies.parent
        if pid and pid in on_date_ids:
            children_of[pid].append(t)
        else:
            roots.append(t)

    lines: List[str] = []

    def emit(task: Task, depth: int) -> None:
        from vault.tasks.parser import _render_task_line, _render_milestone_line
        if task.type == TaskType.MILESTONE:
            lines.append(_render_milestone_line(task))
        else:
            lines.append(_render_task_line(task, depth))
        for note in task.notes:
            lines.append("    " * (depth + 1) + "- " + note)
        for child in children_of.get(task.id, []):
            emit(child, depth + 1)

    for root in roots:
        emit(root, 0)
    return "\n".join(lines)


def _append_to_daily_note(
    vault_root: Path, daily_rel: Path, content: str, count: int,
) -> None:
    absolute = vault_root / daily_rel
    path_arg = f"path={daily_rel.as_posix()}"

    if not absolute.exists():
        r = obsidian_cli("create", "template=daily", path_arg)
        if r.returncode != 0:
            raise RuntimeError(
                f"Daily-note create failed: path={daily_rel}, error={r.stderr.strip()}"
            )
        has_section = False
    else:
        existing = absolute.read_text(encoding="utf-8")
        has_section = any(
            line.strip() == "### Completed Tasks"
            for line in existing.splitlines()
        )

    if not has_section:
        r = obsidian_cli("append", path_arg, "content=### Completed Tasks")
        if r.returncode != 0:
            raise RuntimeError(
                f"Daily-note heading append failed: path={daily_rel}, error={r.stderr.strip()}"
            )

    for chunk in split_on_line_boundaries(content, CONTENT_CHUNK_BYTES):
        r = obsidian_cli("append", path_arg, f"content={chunk}")
        if r.returncode != 0:
            raise RuntimeError(
                f"Daily-note append failed: path={daily_rel}, error={r.stderr.strip()}"
            )

    r = obsidian_cli("property:read", path_arg, "name=completed_tasks")
    current = 0
    if r.returncode == 0:
        stdout = r.stdout.strip()
        if stdout:
            try:
                current = int(stdout)
            except ValueError:
                current = 0
    r = obsidian_cli(
        "property:set", path_arg, "name=completed_tasks",
        f"value={current + count}", "type=number",
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"Daily-note property set failed: path={daily_rel}, error={r.stderr.strip()}"
        )


@router.post(
    "/tasks/archive",
    operation_id="task_archive",
    response_model=ArchiveTasksResponse,
)
def task_archive(
    req: ArchiveTasksRequest, app: App = Depends(get_app),
) -> ArchiveTasksResponse:
    selected = _select_tasks(app, req)
    archivable, reopened = _integrity_reopen(app, selected, req.dry_run)

    archivable = [t for t in archivable if _completed_date(t)]
    by_date = _group_by_date(archivable)
    all_ids = {t.id for t in archivable}

    updates: List[TaskUpdateRecord] = [
        TaskUpdateRecord(id=tid, action=TaskUpdateAction.OPENED)
        for tid in reopened
    ]

    if req.dry_run:
        return ArchiveTasksResponse(
            archived={
                _daily_note_path(d).as_posix(): len(ts)
                for d, ts in by_date.items()
            },
            failures=[],
            updates=updates
            + [
                TaskUpdateRecord(id=t.id, action=TaskUpdateAction.CLOSED)
                for t in archivable
            ],
            dry_run=True,
        )

    archived: Dict[str, int] = {}
    failures: List[str] = []
    vault_root = app.task_parser.vault_root

    for date_str, tasks in by_date.items():
        content = _render_archive_block(tasks, all_ids)
        daily_rel = _daily_note_path(date_str)
        try:
            _append_to_daily_note(vault_root, daily_rel, content, len(tasks))
        except Exception as e:
            log.error("Archive failed for date %s: %s", date_str, e)
            failures.append(date_str)
            continue
        for task in tasks:
            app.task_parser.update(task, ArchiveTask())
            updates.append(
                TaskUpdateRecord(id=task.id, action=TaskUpdateAction.CLOSED)
            )
        archived[daily_rel.as_posix()] = len(tasks)

    return ArchiveTasksResponse(
        archived=archived, failures=failures, updates=updates, dry_run=False,
    )
