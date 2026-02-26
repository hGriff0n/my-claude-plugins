"""
MCP tool handlers for effort operations.
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from models.effort import EffortStatus

log = logging.getLogger(__name__)


def _effort_to_dict(effort, task_count: Optional[int] = None) -> dict:
    d = {
        "name": effort.name,
        "path": str(effort.path),
        "status": effort.status.value,
        "is_focused": effort.is_focused,
        "tasks_file": str(effort.tasks_file) if effort.tasks_file else None,
    }
    if task_count is not None:
        d["task_count"] = task_count
    return d


def register_effort_tools(mcp: FastMCP, cache) -> None:
    """Register all effort-related MCP tools onto the FastMCP instance."""

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
        efforts = cache.list_efforts(status=status)
        results = []
        for effort in efforts:
            count = None
            if include_task_counts and effort.tasks_file:
                tasks = cache.query_tasks(effort=effort.name, status="open,in-progress")
                count = len(tasks)
            results.append(_effort_to_dict(effort, task_count=count))
        return json.dumps(results, indent=2)

    @mcp.tool()
    def effort_get(name: str) -> str:
        """
        Get details for a specific effort including open task summary.

        Args:
            name: Effort name

        Returns:
            JSON object with effort details and task counts by status
        """
        effort = cache.get_effort(name)
        if not effort:
            return json.dumps({"error": f"Effort '{name}' not found"})

        result = _effort_to_dict(effort)

        # Add task summary per status
        if effort.tasks_file:
            for st in ("open", "in-progress", "done"):
                tasks = cache.query_tasks(effort=name, status=st)
                result[f"tasks_{st.replace('-', '_')}"] = len(tasks)

        return json.dumps(result, indent=2)

    @mcp.tool()
    def effort_focus(name: str) -> str:
        """
        Set the focused effort.

        The focused effort represents the currently active project context.
        Focus resets to null when the server restarts.

        Args:
            name: Effort name to focus

        Returns:
            Confirmation JSON
        """
        try:
            cache.set_focus(name)
            effort = cache.get_effort(name)
            return json.dumps(
                {"focused": name, "path": str(effort.path) if effort else None},
                indent=2,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def effort_unfocus() -> str:
        """
        Clear the current focus (set focus to null).

        Returns:
            Confirmation JSON
        """
        cache.set_focus(None)
        return json.dumps({"focused": None})

    @mcp.tool()
    def effort_get_focus() -> str:
        """
        Get the currently focused effort and its open tasks.

        Returns:
            JSON with the focused effort details, or null if none focused
        """
        focus_name = cache.get_focus()
        if not focus_name:
            return json.dumps({"focused": None})

        effort = cache.get_effort(focus_name)
        if not effort:
            return json.dumps({"focused": None, "note": "Focused effort no longer found in vault"})

        result = _effort_to_dict(effort)
        tasks = cache.query_tasks(effort=focus_name, status="open,in-progress")
        result["open_tasks"] = [
            {"id": t.id, "title": t.title, "status": t.status, "section": t.section}
            for t in tasks
        ]
        return json.dumps(result, indent=2)

    @mcp.tool()
    def effort_scan() -> str:
        """
        Rebuild effort state by re-scanning the efforts directory.

        Use this after manually creating, moving, or deleting effort directories.

        Returns:
            JSON summary of discovered efforts
        """
        cache.refresh_efforts()
        efforts = cache.list_efforts()
        return json.dumps(
            {
                "scanned": True,
                "active": [e.name for e in efforts if e.status == EffortStatus.ACTIVE],
                "backlog": [e.name for e in efforts if e.status == EffortStatus.BACKLOG],
            },
            indent=2,
        )
