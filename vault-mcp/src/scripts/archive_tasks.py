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
from datetime import datetime
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
    tasks: List[dict], api_base: str, dry_run: bool = False
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
            if not dry_run:
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
        notes=[(n[0], n[1]) if isinstance(n, (list, tuple)) else (1, n) for n in d.get("notes", [])],
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
    """Return the vault-relative path for a daily note."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return Path("areas") / "journal" / dt.strftime("%Y") / dt.strftime("%m %B") / f"{dt.strftime('%d')}.md"


def append_to_daily_note(
    vault_root: Path, daily_rel_path: Path, content: str
) -> None:
    """
    Append archived task content to a daily note.

    If the file doesn't exist, creates it from the daily note template.
    Appends a '## Completed Tasks' section with the archived content.

    Args:
        vault_root: Absolute path to the vault root (for existence checks)
        daily_rel_path: Vault-relative path to the daily note
        content: Serialized task content to append
    """
    absolute_path = vault_root / daily_rel_path
    if absolute_path.exists():
        r = obsidian_cli(
            "append",
            f"path={daily_rel_path}",
            f"content=## Completed Tasks\n\n{content}",
        )
    else:
        r = obsidian_cli(
            "create",
            "template=daily",
            f"path={daily_rel_path}",
            f"content=## Completed Tasks\n\n{content}",
        )
    if r.returncode != 0:
        raise RuntimeError(
            f"Error archiving to note: path={daily_rel_path}, error={r.stderr.strip()}"
        )


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
    if not any(text == reopen_note for _, text in task.notes):
        task.notes.append((1, reopen_note))


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

def archive_tasks(
    cache: VaultCache, api_base: str = "http://localhost:9400",
    dry_run: bool = False,
) -> dict:
    """
    Main archival orchestrator.

    1. Fetches done tasks via REST API
    2. Identifies archivable tasks, reopens blocked parents
    3. Groups by completion date, serializes, appends to daily notes
    4. Removes archived tasks from source files via cached tree

    When dry_run is True, steps 3-4 are skipped and the return value
    includes a ``tasks`` list describing what would be archived.

    Returns a summary dict with counts for logging.
    """
    # Step 1: Discover
    done_tasks = fetch_done_tasks(api_base)
    log.info("Found %d done tasks", len(done_tasks))

    if not done_tasks:
        return {"archived": 0, "reopened": 0, "daily_notes": 0, "dry_run": dry_run}

    # Step 2: Analyze archivability and reopen blocked parents
    archivable = collect_archivable(done_tasks, api_base, dry_run=dry_run)
    log.info("Archivable tasks: %d", len(archivable))

    if not archivable:
        return {"archived": 0, "reopened": 0, "daily_notes": 0, "dry_run": dry_run}

    # Step 3: Group by date
    by_date = group_by_date(archivable)
    all_archived_ids = _collect_all_ids_flat(archivable)

    if dry_run:
        tasks_preview = [
            {"id": t.get("id"), "title": t.get("title"),
             "completed": t.get("tags", {}).get("completed")}
            for t in archivable
        ]
        return {
            "archived": len(all_archived_ids),
            "daily_notes": len(by_date),
            "dry_run": True,
            "tasks": tasks_preview,
        }

    # TODO: File operations may fail. We should not delete tasks that were not archived
    # because the file failed.
    # Step 4: Append to daily notes (before removing from source — crash safe)
    for date_str, tasks in by_date.items():
        content = build_archive_content(tasks)
        daily_rel = get_daily_note_path(date_str)
        append_to_daily_note(cache.vault_root, daily_rel, content)
        log.info("Archived %d tasks to daily note %s", len(tasks), daily_rel)

    # Step 5: Remove from source files
    # Collect all archived task IDs and resolve their file paths from cache
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
        "dry_run": False,
    }


def _collect_all_ids_flat(tasks: List[dict]) -> Set[str]:
    """Recursively collect all task IDs from a list of task dicts."""
    ids: Set[str] = set()
    for task in tasks:
        if task.get("id"):
            ids.add(task["id"])
        ids.update(_collect_all_ids_flat(task.get("children", [])))
    return ids
