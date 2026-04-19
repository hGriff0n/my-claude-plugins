"""
Archive completed tasks to daily notes.

Runs inside the server process with access to the global VaultCache.
Uses the REST API for task discovery and parent reopening, the obsidian
CLI for daily note path resolution, and the cache for direct tree access
when removing archived tasks from source files.

Core algorithm:
1. Fetch all done tasks via REST API
2. Walk tree: each done-with-completion-date task is individually
   archivable. Done parents with any open descendants are reopened
   (integrity fix) and become non-archivable, but their done
   descendants remain individually archivable.
3. Group archivable tasks by completion date.
4. For each date: render content (nesting a task under its parent only
   if the parent is also being archived on the same date), append to
   the daily note, and — only if the write succeeds — remove that
   date's task IDs from their source files.
"""

import logging
from collections import defaultdict
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


def collect_archivable(
    tasks: List[dict], api_base: str, dry_run: bool = False
) -> Tuple[List[dict], Dict[str, Optional[str]]]:
    """
    Walk the task tree and identify archivable tasks.

    Every done task with a completion date is individually archivable.
    Done parents that still have open descendants are reopened (integrity
    fix) and are NOT included in the archivable list; their done
    descendants remain individually archivable.

    Returns:
        archivable: flat list of task dicts that should be archived
        parent_of: mapping from task ID to its parent task ID in the
            original tree (None for top-level tasks). Used by the
            content builder to decide nesting in the daily note.
    """
    archivable: List[dict] = []
    parent_of: Dict[str, Optional[str]] = {}
    reopened: List[str] = []

    def walk(task: dict, parent_id: Optional[str]) -> None:
        tid = task.get("id")
        if tid:
            parent_of[tid] = parent_id

        is_done = task["status"] == "done"
        completed = task.get("tags", {}).get("completed")

        if is_done and _has_open_descendants(task):
            # Integrity fix: can't be done if a descendant is still open.
            open_ids = _collect_open_child_ids(task)
            if not dry_run:
                reopen_parent(task, open_ids, api_base)
            reopened.append(tid)
            # Parent is no longer done → not archivable. Children may still
            # be individually archivable.
        elif is_done and completed:
            archivable.append(task)

        for child in task.get("children", []):
            walk(child, tid)

    for task in tasks:
        walk(task, None)

    if reopened:
        log.info("Reopened %d parents with open children: %s", len(reopened), reopened)

    return archivable, parent_of


def reopen_parent(task: dict, open_child_ids: List[str], api_base: str) -> None:
    """
    Reopen a done parent that has open children.

    PATCHes the task status back to open (which auto-removes the completed
    tag), then adds blocked references.
    """
    task_id = task["id"]
    log.info("Reopening parent %s due to open children: %s", task_id, open_child_ids)

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


def _dict_to_task_shallow(d: dict) -> Task:
    """Convert a REST API task dict to a Task model, without children."""
    return Task(
        title=d["title"],
        id=d.get("id"),
        status=d["status"],
        tags=dict(d.get("tags", {})),
        notes=[(n[0], n[1]) if isinstance(n, (list, tuple)) else (1, n) for n in d.get("notes", [])],
        children=[],
        indent_level=d.get("indent_level", 0),
    )


def _dict_to_task(d: dict) -> Task:
    """Convert a REST API task dict to a Task model (children included)."""
    task = _dict_to_task_shallow(d)
    task.children = [_dict_to_task(c) for c in d.get("children", [])]
    return task


def build_archive_content(
    tasks_on_date: List[dict], parent_of: Dict[str, Optional[str]]
) -> str:
    """
    Serialize tasks for a single date's daily note.

    A task is nested under its parent only if that parent is also
    being archived on the same date. Otherwise the task renders as a
    top-level entry at indent 0.
    """
    ids_on_date = {t["id"] for t in tasks_on_date if t.get("id")}
    children_of: Dict[str, List[dict]] = defaultdict(list)
    roots: List[dict] = []

    for t in tasks_on_date:
        pid = parent_of.get(t.get("id"))
        if pid in ids_on_date:
            children_of[pid].append(t)
        else:
            roots.append(t)

    def build(d: dict) -> Task:
        task = _dict_to_task_shallow(d)
        task.children = [build(c) for c in children_of.get(d.get("id"), [])]
        return task

    lines: List[str] = []
    for root_dict in roots:
        lines.extend(_serialize_task(build(root_dict), indent_level=0))
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
    Raises RuntimeError if the obsidian CLI reports failure.
    """
    absolute_path = vault_root / daily_rel_path
    if absolute_path.exists():
        r = obsidian_cli(
            "append",
            f"path={daily_rel_path.as_posix()}",
            f"content=## Completed Tasks\n\n{content}",
        )
    else:
        r = obsidian_cli(
            "create",
            "template=daily",
            f"path={daily_rel_path.as_posix()}",
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
    """
    result: List[Task] = []
    for task in tasks:
        if task.id in archived_ids:
            continue
        task.children = _filter_tree_tasks(task.children, archived_ids)
        result.append(task)
    return result


def remove_tasks_from_source(
    cache: VaultCache, file_path: Path, task_ids: Set[str]
) -> None:
    """
    Remove archived tasks from a source file using the cached TaskTree.
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


def _remove_ids_from_sources(
    cache: VaultCache, task_ids: Set[str]
) -> None:
    """Resolve file paths for each ID and remove them from sources."""
    ids_by_file: Dict[Path, Set[str]] = defaultdict(set)
    for tid in task_ids:
        fp = cache.get_task_file(tid)
        if fp:
            ids_by_file[fp].add(tid)
    for fp, tids in ids_by_file.items():
        try:
            remove_tasks_from_source(cache, fp, tids)
            log.info("Removed %d tasks from %s", len(tids), fp)
        except Exception as e:
            log.error("Failed to remove tasks from %s: %s", fp, e)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def archive_tasks(
    cache: VaultCache, api_base: str = "http://localhost:9400",
    dry_run: bool = False,
) -> dict:
    """
    Main archival orchestrator.

    For each completion date, append to the daily note first; only if
    that write succeeds do we remove that date's tasks from their
    source files. A failure on one date does not block archival of
    other dates.
    """
    done_tasks = fetch_done_tasks(api_base)
    log.info("Found %d done tasks", len(done_tasks))

    if not done_tasks:
        return {"archived": 0, "daily_notes": 0, "failed_dates": 0, "dry_run": dry_run}

    archivable, parent_of = collect_archivable(done_tasks, api_base, dry_run=dry_run)
    log.info("Archivable tasks: %d", len(archivable))

    if not archivable:
        return {"archived": 0, "daily_notes": 0, "failed_dates": 0, "dry_run": dry_run}

    by_date = group_by_date(archivable)

    if dry_run:
        tasks_preview = [
            {"id": t.get("id"), "title": t.get("title"),
             "completed": t.get("tags", {}).get("completed")}
            for t in archivable
        ]
        return {
            "archived": len(archivable),
            "daily_notes": len(by_date),
            "failed_dates": 0,
            "dry_run": True,
            "tasks": tasks_preview,
        }

    archived_count = 0
    succeeded_dates = 0
    failed_dates: List[str] = []

    for date_str, tasks in by_date.items():
        content = build_archive_content(tasks, parent_of)
        daily_rel = get_daily_note_path(date_str)
        try:
            append_to_daily_note(cache.vault_root, daily_rel, content)
        except Exception as e:
            log.error(
                "Daily note write failed for %s (%s); leaving %d tasks in source",
                date_str, e, len(tasks),
            )
            failed_dates.append(date_str)
            continue

        succeeded_dates += 1
        ids_for_date = {t["id"] for t in tasks if t.get("id")}
        _remove_ids_from_sources(cache, ids_for_date)
        archived_count += len(ids_for_date)
        log.info("Archived %d tasks to daily note %s", len(tasks), daily_rel)

    return {
        "archived": archived_count,
        "daily_notes": succeeded_dates,
        "failed_dates": len(failed_dates),
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
