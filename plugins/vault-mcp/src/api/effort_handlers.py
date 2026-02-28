"""Effort handler functions shared by MCP tools and REST API."""

import logging
import subprocess
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


# TODO: Move this to utils/
def _obsidian(*args: str) -> subprocess.CompletedProcess:
    """Run an obsidian CLI command. Mockable in tests."""
    return subprocess.run(["obsidian", *args], capture_output=True, text=True)


def handle_effort_create(cache, name: str) -> dict:
    if cache.get_effort(name):
        return {"error": f"Effort '{name}' already exists"}

    # Create CLAUDE.md and README from Obsidian templates (creates the folder implicitly)
    for template, file in [("efforts/claude", "CLAUDE"), ("efforts/readme", "00 README")]:
        r = _obsidian("create", f"template={template}", f"path=\"efforts/{name}/{file}.md\"")
        if r.returncode != 0:
            return {"error": f"obsidian create failed: {r.stderr.strip()}"}

    # If a loose note with the effort name exists anywhere, move it into the folder
    for src_path in [f"efforts/{name}", f"efforts/__ideas/{name}"]:
        r = _obsidian("file", f"path=\"{src_path}\"")
        if r.returncode == 0:
            _obsidian("move", f"path=\"{src_path}\"", f"to=\"efforts/{name}/{name}\"")
            break

    # Create the taskfile
    r = _obsidian("create", f"template=efforts/taskfile", f"path=\"efforts/{name}/01 TASKS.md\"")
    if r.returncode != 0:
        return {"error": f"obsidian create taskfile failed: {r.stderr.strip()}"}

    cache.refresh_efforts()

    effort = cache.get_effort(name)
    if effort:
        return _effort_to_dict(effort)
    return {"name": name, "status": "active", "created": True}


def handle_effort_move(cache, name: str, backlog: bool, archive: bool) -> dict:
    effort = cache.get_effort(name)
    if not effort:
        return {"error": f"Effort '{name}' not found"}

    if backlog and effort.status != EffortStatus.ACTIVE:
        return {"error": f"Effort '{name}' is not active (status: {effort.status.value})"}
    if not backlog and not archive and effort.status != EffortStatus.BACKLOG:
        return {"error": f"Effort '{name}' is not in backlog (status: {effort.status.value})"}

    if backlog:
        dest_base = f"efforts/__backlog/{name}"
    elif archive:
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
            r = _obsidian("move", f"path={rel_to_vault}", f"to={dest_folder}")
            if r.returncode != 0:
                errors.append(str(rel_to_vault))

    if errors:
        return {"error": f"Some files failed to move: {errors}"}

    cache.refresh_efforts()

    effort = cache.get_effort(name)
    if effort:
        return _effort_to_dict(effort)
    return {"name": name, "archived": True} if archive else {"name": name, "moved": True}
