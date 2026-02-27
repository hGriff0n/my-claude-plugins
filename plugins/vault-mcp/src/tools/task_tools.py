"""
Task tool handlers.

Core logic lives in handle_* functions (return dicts).
MCP wrappers in register_task_tools() serialize to JSON strings.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)


def _task_to_dict(task, include_children: bool = True) -> dict:
    """Serialize a Task to a JSON-serializable dict."""
    d = {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "section": task.section,
        "indent_level": task.indent_level,
        "tags": dict(task.tags),
        "notes": list(task.notes),
        "is_atomic": task.is_atomic,
        "is_stub": task.is_stub,
        "is_blocked": task.is_blocked,
        "blocking_ids": task.blocking_ids,
    }
    if include_children and task.children:
        d["children"] = [_task_to_dict(c, include_children=True) for c in task.children]
    return d


# ---------------------------------------------------------------------------
# Handler functions (return dicts, shared by MCP tools and REST API)
# ---------------------------------------------------------------------------


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
    atomic: Optional[bool] = None,
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
        atomic=atomic,
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
    atomic: bool = False,
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
        tags["b"] = blocked_by.replace(" ", "")

    task = cache.add_task(
        Path(file_path),
        title,
        section=section,
        status=status,
        tags=tags,
        parent_id=parent_id,
        atomic=atomic,
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


# ---------------------------------------------------------------------------
# MCP tool registration (thin wrappers)
# ---------------------------------------------------------------------------


def register_task_tools(mcp: FastMCP, cache) -> None:
    """Register all task-related MCP tools onto the FastMCP instance."""

    @mcp.tool()
    def task_list(
        status: str = "open,in-progress",
        effort: Optional[str] = None,
        due_before: Optional[str] = None,
        scheduled_before: Optional[str] = None,
        scheduled_on: Optional[str] = None,
        stub: Optional[bool] = None,
        blocked: Optional[bool] = None,
        atomic: Optional[bool] = None,
        file_path: Optional[str] = None,
        parent_id: Optional[str] = None,
        include_subtasks: bool = False,
        limit: int = 200,
    ) -> str:
        """
        List tasks with optional filtering.

        All tasks (including sub-tasks) are indexed and queryable. Tasks that
        lack an explicit 🆔 tag are auto-assigned a real ID on first scan
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
            atomic: True = only leaf tasks (no children), False = only parent tasks, omit = all
            file_path: Restrict to a specific TASKS.md file path
            parent_id: Only return direct children of this task ID
            include_subtasks: If True, also return sub-tasks of every matched
                task even if the sub-tasks don't match the other filters.
                Useful when you want to see the full breakdown under a
                scheduled/due parent.
            limit: Maximum number of results (default 200)

        Returns:
            JSON array of task objects
        """
        return json.dumps(
            handle_task_list(
                cache,
                status=status,
                effort=effort,
                due_before=due_before,
                scheduled_before=scheduled_before,
                scheduled_on=scheduled_on,
                stub=stub,
                blocked=blocked,
                atomic=atomic,
                file_path=file_path,
                parent_id=parent_id,
                include_subtasks=include_subtasks,
                limit=limit,
            ),
            indent=2,
        )

    @mcp.tool()
    def task_get(task_id: str) -> str:
        """
        Get a single task by ID with full detail including children.

        Args:
            task_id: The 6-character hex task ID (e.g. "a7f3c2")

        Returns:
            JSON task object with nested children, or error message
        """
        return json.dumps(handle_task_get(cache, task_id=task_id), indent=2)

    @mcp.tool()
    def task_add(
        title: str,
        file_path: str,
        section: Optional[str] = None,
        status: str = "open",
        due: Optional[str] = None,
        scheduled: Optional[str] = None,
        estimate: Optional[str] = None,
        blocked_by: Optional[str] = None,
        parent_id: Optional[str] = None,
        atomic: bool = False,
    ) -> str:
        """
        Add a new task to a TASKS.md file.

        The task is auto-assigned a unique ID and a 'created' date.
        By default, tasks are marked #stub (indicating they need subtasks).
        Pass atomic=True for leaf tasks that won't have subtasks.

        Args:
            title: Task title
            file_path: Path to the target TASKS.md file
            section: Section heading to add under (created if missing, defaults to first section)
            status: "open", "in-progress", or "done"
            due: Due date (ISO date or natural language: "Friday", "next Monday", etc.)
            scheduled: Scheduled date (ISO date or natural language)
            estimate: Time estimate (e.g. "2h", "30m", "1d4h")
            blocked_by: Comma-separated IDs of blocking tasks
            parent_id: ID of parent task (makes this a subtask)
            atomic: If True, does not add #stub tag

        Returns:
            JSON object with the new task
        """
        try:
            return json.dumps(
                handle_task_add(
                    cache,
                    title=title,
                    file_path=file_path,
                    section=section,
                    status=status,
                    due=due,
                    scheduled=scheduled,
                    estimate=estimate,
                    blocked_by=blocked_by,
                    parent_id=parent_id,
                    atomic=atomic,
                ),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def task_update(
        task_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        due: Optional[str] = None,
        scheduled: Optional[str] = None,
        estimate: Optional[str] = None,
        blocked_by: Optional[str] = None,
        unblock: Optional[str] = None,
    ) -> str:
        """
        Update task metadata.

        Only fields you pass will be changed. Pass an empty string to clear a field.

        Args:
            task_id: The task ID to update
            title: New title
            status: New status: "open", "in-progress", or "done"
                    Setting to "done" automatically adds a completed date.
            due: New due date (ISO date, natural language, or "" to clear)
            scheduled: New scheduled date (or "" to clear)
            estimate: New time estimate (or "" to clear)
            blocked_by: Comma-separated IDs of tasks to ADD as blockers
            unblock: Comma-separated IDs of blockers to REMOVE

        Returns:
            Updated task JSON or error message
        """
        try:
            return json.dumps(
                handle_task_update(
                    cache,
                    task_id=task_id,
                    title=title,
                    status=status,
                    due=due,
                    scheduled=scheduled,
                    estimate=estimate,
                    blocked_by=blocked_by,
                    unblock=unblock,
                ),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def task_blockers(task_id: str) -> str:
        """
        Show blocking relationships for a task.

        Returns both upstream (what blocks this task) and downstream
        (what this task blocks) relationships.

        Args:
            task_id: The task ID to inspect

        Returns:
            JSON with "blocked_by" and "blocks" lists
        """
        return json.dumps(handle_task_blockers(cache, task_id=task_id), indent=2)

    @mcp.tool()
    def cache_status() -> str:
        """
        Show vault cache statistics.

        Returns:
            JSON with file count, task count, effort count, last scan time, etc.
        """
        return json.dumps(handle_cache_status(cache), indent=2)
