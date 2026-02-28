"""Task handler functions shared by MCP tools and REST API."""

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _task_to_dict(task, include_children: bool = True) -> dict:
    """Serialize a Task to a JSON-serializable dict."""
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


def handle_task_list(
    cache,
    *,
    status: str = "open,in-progress",
    effort: Optional[str] = None,
    due_before: Optional[str] = None,
    scheduled_before: Optional[str] = None,
    scheduled_on: Optional[str] = None,
    stub: Optional[bool] = None,
    blocked: Optional[bool] = None,
    file_path: Optional[str] = None,
    parent_id: Optional[str] = None,
    include_subtasks: bool = False,
    limit: int = 200,
) -> list[dict]:
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


def handle_task_get(cache, *, task_id: str) -> dict:
    entry = cache.get_task(task_id)
    if not entry:
        return {"error": f"Task '{task_id}' not found"}
    task, file_path = entry
    result = _task_to_dict(task, include_children=True)
    result["file_path"] = str(file_path)
    return result


def handle_task_add(
    cache,
    *,
    title: str,
    file_path: str,
    section: Optional[str] = None,
    status: str = "open",
    due: Optional[str] = None,
    scheduled: Optional[str] = None,
    estimate: Optional[str] = None,
    blocked_by: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> dict:
    from utils.dates import parse_date, parse_duration

    tags = {}
    if due:
        parsed = parse_date(due)
        if parsed:
            tags["due"] = parsed
    if scheduled:
        parsed = parse_date(scheduled)
        if parsed:
            tags["scheduled"] = parsed
    if estimate:
        normalized = parse_duration(estimate)
        if normalized:
            tags["estimate"] = normalized
    if blocked_by:
        tags["blocked"] = blocked_by.replace(" ", "")

    task = cache.add_task(
        Path(file_path),
        title,
        section=section,
        status=status,
        tags=tags,
        parent_id=parent_id,
    )
    result = _task_to_dict(task)
    result["file_path"] = file_path
    return result


def handle_task_update(
    cache,
    *,
    task_id: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
    due: Optional[str] = None,
    scheduled: Optional[str] = None,
    estimate: Optional[str] = None,
    blocked_by: Optional[str] = None,
    unblock: Optional[str] = None,
) -> dict:
    from utils.dates import parse_date, parse_duration

    changes = {}
    if title is not None:
        changes["title"] = title
    if status is not None:
        changes["status"] = status
    if due is not None:
        changes["due"] = parse_date(due) if due else ""
    if scheduled is not None:
        changes["scheduled"] = parse_date(scheduled) if scheduled else ""
    if estimate is not None:
        changes["estimate"] = parse_duration(estimate) if estimate else ""
    if blocked_by:
        changes["blocked_by"] = [b.strip() for b in blocked_by.split(",") if b.strip()]
    if unblock:
        changes["unblock"] = [b.strip() for b in unblock.split(",") if b.strip()]

    task = cache.update_task(task_id, **changes)
    if not task:
        return {"error": f"Task '{task_id}' not found"}
    return _task_to_dict(task)


def handle_task_blockers(cache, *, task_id: str) -> dict:
    entry = cache.get_task(task_id)
    if not entry:
        return {"error": f"Task '{task_id}' not found"}

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


def handle_cache_status(cache) -> dict:
    return cache.status()
