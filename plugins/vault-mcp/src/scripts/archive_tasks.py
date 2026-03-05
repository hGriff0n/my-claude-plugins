"""
Archive completed tasks to daily notes.

Runs inside the server process with access to the global VaultCache.
Uses the REST API for task discovery and parent reopening, the obsidian
CLI for daily note path resolution, and the cache for direct tree access
when removing archived tasks from source files.

Core algorithm:
1. Fetch all done tasks via REST API
2. Identify fully-archivable subtrees (all descendants done)
3. Reopen done parents that have open children (via PATCH API)
4. Group archivable tasks by completion date
5. Serialize at normalized indentation and append to daily notes
6. Remove archived tasks from source files via cached TaskTree
"""

import logging
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import httpx

from cache.vault_cache import VaultCache
from models.task import Task
from parsers.task_parser import _serialize_task, write_file
from utils.obsidian import obsidian_cli

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task discovery (REST API)
# ---------------------------------------------------------------------------


def fetch_done_tasks(api_base: str) -> List[dict]:
    """Fetch all completed tasks from the REST API."""
    resp = httpx.get(
        f"{api_base}/app/tasks",
        params={"status": "done", "include_subtasks": "true", "limit": "10000"},
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Archivability analysis
# ---------------------------------------------------------------------------


def _has_open_descendants(task: dict) -> bool:
    """Check if a task dict (from REST API) has any non-done descendants."""
    for child in task.get("children", []):
        if child["status"] != "done":
            return True
        if _has_open_descendants(child):
            return True
    return False


def _collect_open_child_ids(task: dict) -> List[str]:
    """Collect IDs of direct children that are not done."""
    return [
        child["id"]
        for child in task.get("children", [])
        if child["status"] != "done" and child.get("id")
    ]


def _collect_archivable_from_tree(task: dict) -> List[dict]:
    """
    Recursively find archivable subtrees within a task.

    A task is archivable if it is done, has a completed date, and all its
    descendants are also done. If a done parent has open children, we skip
    it and recurse into its children to find archivable leaves.
    """
    if task["status"] != "done" or not task.get("tags", {}).get("completed"):
        # Not done or no completion date — recurse into children
        result = []
        for child in task.get("children", []):
            result.extend(_collect_archivable_from_tree(child))
        return result

    if _has_open_descendants(task):
        # Done parent with open children — skip parent, recurse
        result = []
        for child in task.get("children", []):
            result.extend(_collect_archivable_from_tree(child))
        return result

    # Fully archivable subtree
    return [task]


def collect_archivable(
    tasks: List[dict], api_base: str
) -> List[dict]:
    """
    Identify archivable tasks and reopen done parents with open children.

    Returns the list of fully-archivable task dicts (all descendants done).
    As a side effect, reopens any done parents that have open children by
    PATCHing the REST API and adding blocked tags + reopen notes.
    """
    archivable: List[dict] = []
    reopened: List[str] = []

    for task in tasks:
        if task["status"] != "done":
            continue
        completed = task.get("tags", {}).get("completed")
        if not completed:
            continue

        if _has_open_descendants(task):
            # Reopen this parent
            open_ids = _collect_open_child_ids(task)
            reopen_parent(task, open_ids, api_base)
            reopened.append(task["id"])
            # Recurse into children for individually archivable subtrees
            for child in task.get("children", []):
                archivable.extend(_collect_archivable_from_tree(child))
        else:
            archivable.append(task)

    if reopened:
        log.info("Reopened %d parents with open children: %s", len(reopened), reopened)

    return archivable


def reopen_parent(task: dict, open_child_ids: List[str], api_base: str) -> None:
    """
    Reopen a done parent that has open children.

    PATCHes the task status back to open (which auto-removes the completed
    tag), then adds blocked references and a reopen note.
    """
    task_id = task["id"]
    log.info("Reopening parent %s due to open children: %s", task_id, open_child_ids)

    # PATCH status back to open
    resp = httpx.patch(
        f"{api_base}/app/tasks/{task_id}",
        json={
            "status": "open",
            "blocked_by": ",".join(open_child_ids),
        },
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Grouping and serialization
# ---------------------------------------------------------------------------


def group_by_date(tasks: List[dict]) -> Dict[str, List[dict]]:
    """Group tasks by their completion date."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    for task in tasks:
        date_str = task.get("tags", {}).get("completed", "")
        if date_str:
            groups[date_str].append(task)
    return dict(groups)


def _dict_to_task(d: dict) -> Task:
    """Convert a REST API task dict to a Task model for serialization."""
    children = [_dict_to_task(c) for c in d.get("children", [])]
    return Task(
        title=d["title"],
        id=d.get("id"),
        status=d["status"],
        tags=dict(d.get("tags", {})),
        notes=list(d.get("notes", [])),
        children=children,
        indent_level=d.get("indent_level", 0),
    )


def _filter_same_day_children(task: Task, date_str: str) -> Task:
    """
    Deep-copy a task keeping only children completed on the same date.

    This ensures that when archiving a parent, only same-day completed
    children come along. Children completed on different days are archived
    independently on their own completion date.
    """
    copy = deepcopy(task)
    copy.children = [
        _filter_same_day_children(child, date_str)
        for child in copy.children
        if child.status == "done" and child.tags.get("completed") == date_str
    ]
    return copy


def build_archive_content(tasks: List[dict]) -> str:
    """
    Serialize tasks at normalized indentation for the daily note.

    Each task is rendered at indent level 0, with its same-day children
    at indent level 1, etc.
    """
    lines: List[str] = []
    for task_dict in tasks:
        task = _dict_to_task(task_dict)
        date_str = task.tags.get("completed", "")
        filtered = _filter_same_day_children(task, date_str)
        lines.extend(_serialize_task(filtered, indent_level=0))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daily note operations
# ---------------------------------------------------------------------------


def get_daily_note_path(date_str: str) -> Path:
    """Resolve the daily note file path for a given date via obsidian CLI."""
    r = obsidian_cli("daily", f"date={date_str}", "info=path")
    if r.returncode != 0:
        raise RuntimeError(
            f"Failed to get daily note path for {date_str}: {r.stderr.strip()}"
        )
    return Path(r.stdout.strip())


def append_to_daily_note(daily_path: Path, content: str) -> None:
    """
    Append archived task content to a daily note.

    If the file doesn't exist, creates it. If a '## Completed Tasks'
    section already exists, appends tasks at the end of that section.
    Otherwise, appends a new section at the end of the file.
    """
    if not daily_path.exists():
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily_path.write_text("", encoding="utf-8")

    existing = daily_path.read_text(encoding="utf-8")
    lines = existing.splitlines()

    # Find existing "## Completed Tasks" section
    section_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Completed Tasks":
            section_idx = i
            break

    if section_idx is not None:
        # Find the end of the section (next ## heading or EOF)
        insert_idx = len(lines)
        for i in range(section_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_idx = i
                break
        # Insert content before the next section (or at EOF)
        content_lines = content.splitlines()
        lines[insert_idx:insert_idx] = content_lines
    else:
        # Append new section
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("## Completed Tasks")
        lines.append("")
        lines.extend(content.splitlines())

    daily_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Source file cleanup
# ---------------------------------------------------------------------------


def _filter_tree_tasks(tasks: List[Task], archived_ids: Set[str]) -> List[Task]:
    """
    Recursively filter a list of tasks, removing those in archived_ids.

    Returns a new list with archived tasks removed and remaining tasks
    having their children filtered recursively.
    """
    result: List[Task] = []
    for task in tasks:
        if task.id in archived_ids:
            continue
        task.children = _filter_tree_tasks(task.children, archived_ids)
        result.append(task)
    return result


def _add_reopen_note(task: Task) -> None:
    """Add a reopen note to a task if not already present."""
    reopen_note = "**Reopened due to open child tasks**"
    if reopen_note not in task.notes:
        task.notes.append(reopen_note)


def remove_tasks_from_source(
    cache: VaultCache, file_path: Path, task_ids: Set[str]
) -> None:
    """
    Remove archived tasks from a source file using the cached TaskTree.

    Accesses the cache's in-memory tree directly, filters out archived
    tasks, and writes back. The file watcher will detect the mtime change
    and re-index automatically.
    """
    with cache._lock:
        cached = cache._files.get(file_path)
        if not cached:
            log.warning("File not in cache, skipping: %s", file_path)
            return

        tree = cached.tree
        for section in tree.sections:
            section.tasks = _filter_tree_tasks(section.tasks, task_ids)

        write_file(file_path, tree)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# TODO: Move to MCP?
# TODO: Add functionality to fill-in missing metadata
def archive_tasks(
    cache: VaultCache, api_base: str = "http://localhost:9400"
) -> dict:
    """
    Main archival orchestrator.

    1. Fetches done tasks via REST API
    2. Identifies archivable tasks, reopens blocked parents
    3. Groups by completion date, serializes, appends to daily notes
    4. Removes archived tasks from source files via cached tree

    Returns a summary dict with counts for logging.
    """
    # Step 1: Discover
    done_tasks = fetch_done_tasks(api_base)
    log.info("Found %d done tasks", len(done_tasks))

    if not done_tasks:
        return {"archived": 0, "reopened": 0, "daily_notes": 0}

    # Step 2: Analyze archivability and reopen blocked parents
    archivable = collect_archivable(done_tasks, api_base)
    log.info("Archivable tasks: %d", len(archivable))

    if not archivable:
        return {"archived": 0, "reopened": 0, "daily_notes": 0}

    # Step 3: Group by date
    by_date = group_by_date(archivable)

    # Step 4: Append to daily notes (before removing from source — crash safe)
    for date_str, tasks in by_date.items():
        content = build_archive_content(tasks)
        daily_path = get_daily_note_path(date_str)
        append_to_daily_note(daily_path, content)
        log.info("Archived %d tasks to daily note %s", len(tasks), daily_path)

    # Step 5: Remove from source files
    # Collect all archived task IDs and resolve their file paths from cache
    all_archived_ids = _collect_all_ids_flat(archivable)
    archived_ids_by_file: Dict[Path, Set[str]] = defaultdict(set)
    for task_id in all_archived_ids:
        file_path = cache.get_task_file(task_id)
        if file_path:
            archived_ids_by_file[file_path].add(task_id)

    for file_path, task_ids in archived_ids_by_file.items():
        remove_tasks_from_source(cache, file_path, task_ids)
        log.info("Removed %d tasks from %s", len(task_ids), file_path)

    return {
        "archived": len(all_archived_ids),
        "daily_notes": len(by_date),
    }


def _collect_all_ids_flat(tasks: List[dict]) -> Set[str]:
    """Recursively collect all task IDs from a list of task dicts."""
    ids: Set[str] = set()
    for task in tasks:
        if task.get("id"):
            ids.add(task["id"])
        ids.update(_collect_all_ids_flat(task.get("children", [])))
    return ids
