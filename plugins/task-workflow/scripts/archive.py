#!/usr/bin/env python3
"""
Archive completed tasks to keep TASKS.md clean.

Reads tasks from the cache (re-parsing if stale), filters by completion date,
writes archived tasks to an archive file, and updates TASKS.md + cache.

Usage:
    archive.py [--older-than DAYS] [--dry-run]
"""

import copy
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from cache import TaskCacheInterface
from models import Task, TaskTree
from parser import parse_file, write_file

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "assets" / "templates"
ARCHIVE_TEMPLATE = TEMPLATE_DIR / "archive.template.md"


def ensure_fresh(cache: TaskCacheInterface, file_path: Path) -> Tuple[List[str], TaskTree]:
    """
    Ensure cache is up-to-date for a file, re-parsing if stale.

    Args:
        cache: Cache instance
        file_path: Path to TASKS.md file

    Returns:
        Tuple of (frontmatter, tree) from cache
    """
    if cache.is_file_stale(file_path):
        frontmatter, tree = parse_file(file_path)
        cache.update_file(file_path, tree, frontmatter)

    return cache.get_frontmatter(file_path), cache.get_tree(file_path)


def should_archive(task: Task, older_than_days: int) -> bool:
    """
    Check if a task should be archived.

    Args:
        task: Task to check
        older_than_days: Archive tasks completed more than this many days ago

    Returns:
        True if task should be archived
    """
    if task.status != "done":
        return False

    completion_date_str = task.tags.get('completed')
    if not completion_date_str:
        return False

    try:
        completion_date = datetime.fromisoformat(completion_date_str).date()
        cutoff_date = (datetime.now() - timedelta(days=older_than_days)).date()
        return completion_date < cutoff_date
    except ValueError:
        return False


def collect_archived_tasks(tree: TaskTree, older_than_days: int) -> Tuple[List[Task], TaskTree]:
    """
    Collect tasks to archive and build a new tree without them.

    Non-mutating: returns new Task/TaskTree objects, leaving the input intact.

    Args:
        tree: Original task tree
        older_than_days: Archive tasks completed more than this many days ago

    Returns:
        Tuple of (archived_tasks, remaining_tree)
    """
    archived = []

    def flatten(task: Task) -> List[Task]:
        """Collect a task and all its descendants."""
        result = [task]
        for child in task.children:
            result.extend(flatten(child))
        return result

    def process_task(task: Task) -> Optional[Task]:
        """Recursively filter a task. Returns None if fully archived."""
        if should_archive(task, older_than_days):
            archived.extend(flatten(task))
            return None

        # Keep this task, but filter its children
        remaining_children = []
        for child in task.children:
            kept = process_task(child)
            if kept is not None:
                remaining_children.append(kept)

        # Only create a copy if children changed
        if len(remaining_children) != len(task.children):
            filtered = copy.copy(task)
            filtered.children = remaining_children
            return filtered

        return task

    remaining = []
    for root_task in tree.tasks:
        kept = process_task(root_task)
        if kept is not None:
            remaining.append(kept)

    return archived, TaskTree(tasks=remaining, file_path=tree.file_path)


def format_archive_section(tasks: List[Task], date: datetime) -> str:
    """
    Format archived tasks as a markdown section.

    Args:
        tasks: Tasks to include
        date: Archive date

    Returns:
        Markdown string
    """
    lines = [f"## Archived on {date.date().isoformat()}", ""]
    for task in tasks:
        lines.append(str(task))
    lines.append("")
    return "\n".join(lines)


def archive_tasks(
    cache: TaskCacheInterface,
    tasks_file: Path,
    archive_file: Path,
    older_than_days: int,
    dry_run: bool = False,
) -> dict:
    """
    Archive completed tasks to a separate file.

    Args:
        cache: Cache instance (used for reading, updated after writing)
        tasks_file: Path to TASKS.md
        archive_file: Path to archive file
        older_than_days: Archive tasks completed more than this many days ago
        dry_run: If True, don't modify files

    Returns:
        Dict with status, count, message, and optionally tasks
    """
    if not tasks_file.exists():
        return {"status": "error", "message": f"Tasks file not found: {tasks_file}"}

    # Ensure cache is fresh, then read from it
    frontmatter, tree = ensure_fresh(cache, tasks_file)

    # Determine what to archive
    archived_tasks, remaining_tree = collect_archived_tasks(tree, older_than_days)

    if not archived_tasks:
        return {"status": "success", "count": 0, "message": "No tasks to archive"}

    if dry_run:
        return {
            "status": "success",
            "count": len(archived_tasks),
            "message": f"Would archive {len(archived_tasks)} task(s) (dry run)",
            "tasks": archived_tasks,
        }

    # Build archive section
    now = datetime.now()
    new_section = format_archive_section(archived_tasks, now)

    # Create archive file from template if it doesn't exist
    if not archive_file.exists():
        shutil.copy(ARCHIVE_TEMPLATE, archive_file)

    # Append archived tasks
    with open(archive_file, 'a', encoding='utf-8') as f:
        f.write("\n" + new_section)

    # Write updated TASKS.md and refresh cache
    write_file(tasks_file, frontmatter, remaining_tree)
    cache.update_file(tasks_file, remaining_tree, frontmatter)

    return {
        "status": "success",
        "count": len(archived_tasks),
        "message": f"Archived {len(archived_tasks)} task(s) to {archive_file}",
    }
