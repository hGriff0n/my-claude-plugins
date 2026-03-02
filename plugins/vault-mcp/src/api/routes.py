"""REST API routes for vault-mcp.

These routes serve as the single source of truth for both the REST API
and MCP tools (auto-generated via FastMCP.from_fastapi).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.task_handlers import (
    handle_cache_status,
    handle_task_add,
    handle_task_blockers,
    handle_task_get,
    handle_task_list,
    handle_task_update,
)
from api.effort_handlers import (
    handle_effort_create,
    handle_effort_get,
    handle_effort_list,
    handle_effort_move,
    handle_effort_scan,
)


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
# Route registration
# ---------------------------------------------------------------------------


def register_routes(app_router: APIRouter, cache) -> None:
    """Attach all REST routes that use the shared cache."""

    # --- Task routes ---

    @app_router.get("/tasks", operation_id="task_list")
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
        return handle_task_list(
            cache,
            status=status,
            effort=effort,
            due_before=due_before,
            scheduled_before=scheduled_before,
            scheduled_on=scheduled_on,
            stub=stub,
            blocked=blocked,
            file_path=file_path,
            parent_id=parent_id,
            include_subtasks=include_subtasks,
            limit=limit,
        )

    @app_router.get("/tasks/{task_id}", operation_id="task_get")
    def get_task(task_id: str):
        """Get a single task by ID with full detail including children.

        Args:
            task_id: The 6-character hex task ID (e.g. "a7f3c2")
        """
        result = handle_task_get(cache, task_id=task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.post("/tasks", status_code=201, operation_id="task_add")
    def add_task(body: TaskAddBody):
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
            return handle_task_add(cache, **body.model_dump())
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app_router.patch("/tasks/{task_id}", operation_id="task_update")
    def update_task(task_id: str, body: TaskUpdateBody):
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
            result = handle_task_update(cache, task_id=task_id, **body.model_dump())
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.get("/tasks/{task_id}/blockers", operation_id="task_blockers")
    def get_blockers(task_id: str):
        """Show blocking relationships for a task.

        Returns both upstream (what blocks this task) and downstream
        (what this task blocks) relationships.

        Args:
            task_id: The task ID to inspect
        """
        result = handle_task_blockers(cache, task_id=task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.get("/cache/status", operation_id="cache_status")
    def get_cache_status():
        """Show vault cache statistics including file count, task count, and effort count."""
        return handle_cache_status(cache)

    # --- Effort routes ---

    @app_router.get("/efforts", operation_id="effort_list")
    def list_efforts(
        status: Optional[str] = Query(None),
        include_task_counts: bool = Query(False),
    ):
        """List efforts.

        Args:
            status: Filter by status: "active", "backlog", or omit for all
            include_task_counts: If True, include the count of non-done tasks per effort
        """
        return handle_effort_list(
            cache, status=status, include_task_counts=include_task_counts
        )

    @app_router.post("/efforts", status_code=201, operation_id="effort_create")
    def create_effort(body: EffortCreateBody):
        """Create a new active effort with CLAUDE.md, README, and TASKS.md from templates.

        Args:
            name: Effort name (used as directory name)
        """
        try:
            result = handle_effort_create(cache, name=body.name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app_router.post("/efforts/scan", operation_id="effort_scan")
    def scan_efforts():
        """Rebuild effort state by re-scanning the efforts directory.

        Use this after manually creating, moving, or deleting effort directories.
        """
        return handle_effort_scan(cache)

    @app_router.get("/efforts/{name}", operation_id="effort_get")
    def get_effort(name: str):
        """Get details for a specific effort including open task summary.

        Args:
            name: Effort name
        """
        result = handle_effort_get(cache, name=name)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.post("/efforts/{name}/move", operation_id="effort_move")
    def move_effort(name: str, body: EffortMoveBody):
        """Move an effort between active, backlog, and archive states.

        Pass backlog=true to move an active effort to __backlog/.
        Pass archive=true to move any effort to __archive/.
        Pass neither flag to activate a backlog effort.

        Args:
            name: Effort name
            backlog: Move active effort to __backlog/
            archive: Move effort to __archive/ (permanent, removes from index)
        """
        try:
            result = handle_effort_move(
                cache, name=name, backlog=body.backlog, archive=body.archive
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            status_code = 404 if "not found" in result["error"] else 400
            raise HTTPException(status_code=status_code, detail=result["error"])
        return result
