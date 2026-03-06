"""REST API routes for vault-mcp.

These routes serve as the single source of truth for both the REST API
and MCP tools (auto-generated via FastMCP.from_fastapi).
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_cache
from models.effort import EffortStatus
from utils.dates import parse_date, parse_duration
from utils.obsidian import obsidian_cli

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------


class TaskAddBody(BaseModel):
    title: str
    file_path: str
    section: Optional[str] = None
    status: str = "open"
    due: Optional[str] = None
    scheduled: Optional[str] = None
    estimate: Optional[str] = None
    blocked_by: Optional[str] = None
    parent_id: Optional[str] = None


class TaskUpdateBody(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    due: Optional[str] = None
    scheduled: Optional[str] = None
    estimate: Optional[str] = None
    blocked_by: Optional[str] = None
    unblock: Optional[str] = None


class EffortCreateBody(BaseModel):
    name: str


class EffortMoveBody(BaseModel):
    backlog: bool = False
    archive: bool = False


# ---------------------------------------------------------------------------
# Serializer helpers
# ---------------------------------------------------------------------------


def _task_to_dict(task, include_children: bool = True) -> dict:
    d = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "ref": task.ref,
        "section": task.section,
        "indent_level": task.indent_level,
        "tags": dict(task.tags),
        "notes": list(task.notes),
        "is_stub": task.is_stub,
        "is_blocked": task.is_blocked,
        "blocking_ids": task.blocking_ids,
    }
    if include_children and task.children:
        d["children"] = [_task_to_dict(c, include_children=True) for c in task.children]
    return d


def _effort_to_dict(effort, task_count: Optional[int] = None) -> dict:
    d = {
        "name": effort.name,
        "path": str(effort.path),
        "status": effort.status.value,
        "tasks_file": str(effort.tasks_file) if effort.tasks_file else None,
    }
    if task_count is not None:
        d["task_count"] = task_count
    return d


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------


@router.get("/tasks", operation_id="task_list")
def list_tasks(
    status: str = Query("open,in-progress"),
    effort: Optional[str] = Query(None),
    due_before: Optional[str] = Query(None),
    scheduled_before: Optional[str] = Query(None),
    scheduled_on: Optional[str] = Query(None),
    stub: Optional[bool] = Query(None),
    blocked: Optional[bool] = Query(None),
    file_path: Optional[str] = Query(None),
    parent_id: Optional[str] = Query(None),
    include_subtasks: bool = Query(False),
    limit: int = Query(200),
    cache=Depends(get_cache),
):
    """List tasks with optional filtering.

    All tasks (including sub-tasks) are indexed and queryable. Tasks that
    lack an explicit ID tag are auto-assigned a real ID on first scan
    (the ID is written back to disk so it persists).

    Args:
        status: Comma-separated statuses to include. Default: "open,in-progress".
                Use "open,in-progress,done" for all, or "done" for completed only.
        effort: Filter to tasks belonging to a specific effort (by name)
        due_before: ISO date (YYYY-MM-DD) — return tasks due on or before this date
        scheduled_before: ISO date (YYYY-MM-DD) — return tasks scheduled on or before this date
        scheduled_on: ISO date (YYYY-MM-DD) — return tasks scheduled for exactly this date
        stub: True = only stubs, False = exclude stubs, omit = include all
        blocked: True = only blocked tasks, False = exclude blocked, omit = all
        file_path: Restrict to a specific TASKS.md file path
        parent_id: Only return direct children of this task ID
        include_subtasks: If True, also return sub-tasks of every matched
            task even if the sub-tasks don't match the other filters.
        limit: Maximum number of results (default 200)
    """
    fp = Path(file_path) if file_path else None
    tasks = cache.query_tasks(
        status=status,
        effort=effort,
        due_before=due_before,
        scheduled_before=scheduled_before,
        scheduled_on=scheduled_on,
        stub=stub,
        blocked=blocked,
        file_path=fp,
        parent_id=parent_id,
        include_subtasks=include_subtasks,
        limit=limit,
    )
    return [_task_to_dict(t) for t in tasks]


@router.get("/tasks/{task_id}", operation_id="task_get")
def get_task(task_id: str, cache=Depends(get_cache)):
    """Get a single task by ID with full detail including children.

    Args:
        task_id: The 6-character hex task ID (e.g. "a7f3c2")
    """
    entry = cache.get_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    task, file_path = entry
    result = _task_to_dict(task, include_children=True)
    result["file_path"] = str(file_path)
    return result


@router.post("/tasks", status_code=201, operation_id="task_add")
def add_task(body: TaskAddBody, cache=Depends(get_cache)):
    """Add a new task to a TASKS.md file.

    The task is auto-assigned a unique ID and a 'created' date.

    Args:
        title: Task title
        file_path: Path to the target TASKS.md file
        section: Section heading to add under (created if missing)
        status: "open", "in-progress", or "done"
        due: Due date (ISO date or natural language: "Friday", "next Monday", etc.)
        scheduled: Scheduled date (ISO date or natural language)
        estimate: Time estimate (e.g. "2h", "30m", "1d4h")
        blocked_by: Comma-separated IDs of blocking tasks
        parent_id: ID of parent task (makes this a subtask)
    """
    try:
        tags = {}
        if body.due:
            parsed = parse_date(body.due)
            if parsed:
                tags["due"] = parsed
        if body.scheduled:
            parsed = parse_date(body.scheduled)
            if parsed:
                tags["scheduled"] = parsed
        if body.estimate:
            normalized = parse_duration(body.estimate)
            if normalized:
                tags["estimate"] = normalized
        if body.blocked_by:
            tags["blocked"] = body.blocked_by.replace(" ", "")

        task = cache.add_task(
            Path(body.file_path),
            body.title,
            section=body.section,
            status=body.status,
            tags=tags,
            parent_id=body.parent_id,
        )
        result = _task_to_dict(task)
        result["file_path"] = body.file_path
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/tasks/{task_id}", operation_id="task_update")
def update_task(task_id: str, body: TaskUpdateBody, cache=Depends(get_cache)):
    """Update task metadata.

    Only fields you pass will be changed. Pass an empty string to clear a field.

    Args:
        task_id: The task ID to update
        title: New title
        status: New status: "open", "in-progress", or "done"
        due: New due date (ISO date, natural language, or "" to clear)
        scheduled: New scheduled date (or "" to clear)
        estimate: New time estimate (or "" to clear)
        blocked_by: Comma-separated IDs of tasks to ADD as blockers
        unblock: Comma-separated IDs of blockers to REMOVE
    """
    try:
        changes = {}
        if body.title is not None:
            changes["title"] = body.title
        if body.status is not None:
            changes["status"] = body.status
        if body.due is not None:
            changes["due"] = parse_date(body.due) if body.due else ""
        if body.scheduled is not None:
            changes["scheduled"] = parse_date(body.scheduled) if body.scheduled else ""
        if body.estimate is not None:
            changes["estimate"] = parse_duration(body.estimate) if body.estimate else ""
        if body.blocked_by:
            changes["blocked_by"] = [b.strip() for b in body.blocked_by.split(",") if b.strip()]
        if body.unblock:
            changes["unblock"] = [b.strip() for b in body.unblock.split(",") if b.strip()]

        task = cache.update_task(task_id, **changes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return _task_to_dict(task)


@router.get("/tasks/{task_id}/blockers", operation_id="task_blockers")
def get_blockers(task_id: str, cache=Depends(get_cache)):
    """Show blocking relationships for a task.

    Returns both upstream (what blocks this task) and downstream
    (what this task blocks) relationships.

    Args:
        task_id: The task ID to inspect
    """
    entry = cache.get_task(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    task, _ = entry
    all_ids = cache.get_all_task_ids()

    blocked_by = []
    for bid in task.blocking_ids:
        blocker_entry = cache.get_task(bid)
        if blocker_entry:
            t, _ = blocker_entry
            blocked_by.append({"id": t.id, "title": t.title, "status": t.status})

    blocks = []
    for tid in all_ids:
        other_entry = cache.get_task(tid)
        if other_entry:
            other, _ = other_entry
            if task_id in other.blocking_ids:
                blocks.append({"id": other.id, "title": other.title, "status": other.status})

    return {
        "task_id": task_id,
        "title": task.title,
        "blocked_by": blocked_by,
        "blocks": blocks,
    }


@router.get("/cache/status", operation_id="cache_status")
def get_cache_status(cache=Depends(get_cache)):
    """Show vault cache statistics including file count, task count, and effort count."""
    return cache.status()


# ---------------------------------------------------------------------------
# Effort routes
# ---------------------------------------------------------------------------


@router.get("/efforts", operation_id="effort_list")
def list_efforts(
    status: Optional[str] = Query(None),
    include_task_counts: bool = Query(False),
    cache=Depends(get_cache),
):
    """List efforts.

    Args:
        status: Filter by status: "active", "backlog", or omit for all
        include_task_counts: If True, include the count of non-done tasks per effort
    """
    efforts = cache.list_efforts(status=status)
    results = []
    for effort in efforts:
        count = None
        if include_task_counts and effort.tasks_file:
            tasks = cache.query_tasks(effort=effort.name, status="open,in-progress")
            count = len(tasks)
        results.append(_effort_to_dict(effort, task_count=count))
    return results


@router.post("/efforts", status_code=201, operation_id="effort_create")
def create_effort(body: EffortCreateBody, cache=Depends(get_cache)):
    """Create a new active effort with CLAUDE.md, README, and TASKS.md from templates.

    Args:
        name: Effort name (used as directory name)
    """
    name = body.name
    if cache.get_effort(name):
        raise HTTPException(status_code=400, detail=f"Effort '{name}' already exists")

    try:
        for template, file in [("efforts/claude", "CLAUDE"), ("efforts/readme", "00 README")]:
            r = obsidian_cli("create", f"template={template}", f"path=\"efforts/{name}/{file}.md\"")
            if r.returncode != 0:
                raise HTTPException(status_code=400, detail=f"obsidian create failed: {r.stderr.strip()}")

        for src_path in [f"efforts/{name}", f"efforts/__ideas/{name}"]:
            r = obsidian_cli("file", f"path=\"{src_path}\"")
            if r.returncode == 0:
                obsidian_cli("move", f"path=\"{src_path}\"", f"to=\"efforts/{name}/{name}\"")
                break

        r = obsidian_cli("create", f"template=efforts/taskfile", f"path=\"efforts/{name}/01 TASKS.md\"")
        if r.returncode != 0:
            raise HTTPException(status_code=400, detail=f"obsidian create taskfile failed: {r.stderr.strip()}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    cache.refresh_efforts()
    effort = cache.get_effort(name)
    if effort:
        return _effort_to_dict(effort)
    return {"name": name, "status": "active", "created": True}


@router.post("/efforts/scan", operation_id="effort_scan")
def scan_efforts(cache=Depends(get_cache)):
    """Rebuild effort state by re-scanning the efforts directory.

    Use this after manually creating, moving, or deleting effort directories.
    """
    cache.refresh_efforts()
    efforts = cache.list_efforts()
    return {
        "scanned": True,
        "active": [e.name for e in efforts if e.status == EffortStatus.ACTIVE],
        "backlog": [e.name for e in efforts if e.status == EffortStatus.BACKLOG],
    }


@router.get("/efforts/{name}", operation_id="effort_get")
def get_effort(name: str, cache=Depends(get_cache)):
    """Get details for a specific effort including open task summary.

    Args:
        name: Effort name
    """
    effort = cache.get_effort(name)
    if not effort:
        raise HTTPException(status_code=404, detail=f"Effort '{name}' not found")

    result = _effort_to_dict(effort)
    if effort.tasks_file:
        for st in ("open", "in-progress", "done"):
            tasks = cache.query_tasks(effort=name, status=st)
            result[f"tasks_{st.replace('-', '_')}"] = len(tasks)
    return result


@router.post("/efforts/{name}/move", operation_id="effort_move")
def move_effort(name: str, body: EffortMoveBody, cache=Depends(get_cache)):
    """Move an effort between active, backlog, and archive states.

    Pass backlog=true to move an active effort to __backlog/.
    Pass archive=true to move any effort to __archive/.
    Pass neither flag to activate a backlog effort.

    Args:
        name: Effort name
        backlog: Move active effort to __backlog/
        archive: Move effort to __archive/ (permanent, removes from index)
    """
    effort = cache.get_effort(name)
    if not effort:
        raise HTTPException(status_code=404, detail=f"Effort '{name}' not found")

    if body.backlog and effort.status != EffortStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Effort '{name}' is not active (status: {effort.status.value})")
    if not body.backlog and not body.archive and effort.status != EffortStatus.BACKLOG:
        raise HTTPException(status_code=400, detail=f"Effort '{name}' is not in backlog (status: {effort.status.value})")

    if body.backlog:
        dest_base = f"efforts/__backlog/{name}"
    elif body.archive:
        dest_base = f"efforts/__archive/{name}"
    else:
        dest_base = f"efforts/{name}"

    # Iterative DFS: push subdirectories onto the stack so every file at every
    # depth is moved individually (obsidian move doesn't support folders).
    folders = [effort.path]
    vault_root = cache.vault_root
    errors = []
    while folders:
        folder = folders.pop()
        for item in folder.iterdir():
            if item.is_dir():
                folders.append(item)
                continue
            rel_to_vault = item.relative_to(vault_root)
            rel_to_effort = item.relative_to(effort.path)
            parent = rel_to_effort.parent
            dest_folder = f"{dest_base}/{parent}" if str(parent) != "." else dest_base
            r = obsidian_cli("move", f"path={rel_to_vault}", f"to={dest_folder}")
            if r.returncode != 0:
                errors.append(str(rel_to_vault))

    if errors:
        raise HTTPException(status_code=400, detail=f"Some files failed to move: {errors}")

    cache.refresh_efforts()
    effort = cache.get_effort(name)
    if effort:
        return _effort_to_dict(effort)
    return {"name": name, "archived": True} if body.archive else {"name": name, "moved": True}
