"""MCP tool registration for vault-mcp."""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

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

log = logging.getLogger(__name__)


def register_tools(mcp: FastMCP, cache) -> None:
    """Register all MCP tools onto the FastMCP instance."""

    # ------------------------------------------------------------------
    # Task tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def task_list(
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
    ) -> str:
        """
        Add a new task to a TASKS.md file.

        The task is auto-assigned a unique ID and a 'created' date.
        Tasks are marked #stub by default (indicating they need subtasks).

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

    # ------------------------------------------------------------------
    # Effort tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def effort_list(
        status: Optional[str] = None,
        include_task_counts: bool = False,
    ) -> str:
        """
        List efforts.

        Args:
            status: Filter by status: "active", "backlog", or omit for all
            include_task_counts: If True, include the count of non-done tasks per effort

        Returns:
            JSON array of effort objects
        """
        return json.dumps(
            handle_effort_list(cache, status=status, include_task_counts=include_task_counts),
            indent=2,
        )

    @mcp.tool()
    def effort_get(name: str) -> str:
        """
        Get details for a specific effort including open task summary.

        Args:
            name: Effort name

        Returns:
            JSON object with effort details and task counts by status
        """
        return json.dumps(handle_effort_get(cache, name=name), indent=2)

    @mcp.tool()
    def effort_scan() -> str:
        """
        Rebuild effort state by re-scanning the efforts directory.

        Use this after manually creating, moving, or deleting effort directories.

        Returns:
            JSON summary of discovered efforts
        """
        return json.dumps(handle_effort_scan(cache), indent=2)

    @mcp.tool()
    def effort_create(name: str) -> str:
        """
        Create a new active effort with CLAUDE.md, README, and TASKS.md from templates.

        If a note named {name} exists under efforts/ or efforts/__ideas/, it is moved
        into the new effort folder.

        Args:
            name: Effort name (used as directory name)

        Returns:
            JSON effort object or error
        """
        try:
            return json.dumps(handle_effort_create(cache, name=name), indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def effort_move(
        name: str,
        backlog: bool = False,
        archive: bool = False,
    ) -> str:
        """
        Move an effort between active, backlog, and archive states.

        Pass backlog=true to move an active effort to __backlog/.
        Pass archive=true to move any effort to __archive/ (removes from tracking).
        Pass neither flag to activate a backlog effort.

        Files are moved individually via the obsidian CLI to preserve wikilinks.

        Args:
            name: Effort name
            backlog: Move active effort to __backlog/
            archive: Move effort to __archive/ (permanent, removes from index)

        Returns:
            JSON updated effort object or error
        """
        try:
            return json.dumps(
                handle_effort_move(cache, name=name, backlog=backlog, archive=archive),
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
