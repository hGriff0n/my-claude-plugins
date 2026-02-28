"""Effort handler functions shared by MCP tools and REST API."""

import logging
from typing import Optional

from models.effort import EffortStatus

log = logging.getLogger(__name__)


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


def handle_effort_list(
    cache,
    status: Optional[str] = None,
    include_task_counts: bool = False,
) -> list[dict]:
    efforts = cache.list_efforts(status=status)
    results = []
    for effort in efforts:
        count = None
        if include_task_counts and effort.tasks_file:
            tasks = cache.query_tasks(effort=effort.name, status="open,in-progress")
            count = len(tasks)
        results.append(_effort_to_dict(effort, task_count=count))
    return results


def handle_effort_get(cache, name: str) -> dict:
    effort = cache.get_effort(name)
    if not effort:
        return {"error": f"Effort '{name}' not found"}

    result = _effort_to_dict(effort)
    if effort.tasks_file:
        for st in ("open", "in-progress", "done"):
            tasks = cache.query_tasks(effort=name, status=st)
            result[f"tasks_{st.replace('-', '_')}"] = len(tasks)
    return result


def handle_effort_scan(cache) -> dict:
    cache.refresh_efforts()
    efforts = cache.list_efforts()
    return {
        "scanned": True,
        "active": [e.name for e in efforts if e.status == EffortStatus.ACTIVE],
        "backlog": [e.name for e in efforts if e.status == EffortStatus.BACKLOG],
    }

def handle_effort_create(cache, name: str) -> dict:
    # TODO: Need to move "assets" to obsidian's template dir
    # TODO: `obsidian create template=effort-readme path=efforts/{name}/00 README.md`
    # TODO: `obsidian create template=effort-claude path=efforts/{name}/CLAUDE.md`
    # TODO: if `obsidian file path=efforts/{name}` or `obsidian file path=efforts/__ideas/{name}`
        #       `obsidian move path=... to=efforts/{name}/{name}`
    # TODO: update cache to add the new effort as an active effort
    # TODO: `obsidian create template=taskfile path=efforts/{name}/01 TASKS.md`

def handle_effort_move(cache, name: str, backlog: bool, archive: bool) -> dict:
    # TODO: if `backlog` this is moving an active effort to backlog
    # TODO: if `archive` this is moving an active/backlog effort to archive
    # TODO: otherwise this is moving a backlog effort to active
    # Moving must use `obsidian move` for all files to preserve links. this doesn't work on folders so
    # we must recursively iterate over all files