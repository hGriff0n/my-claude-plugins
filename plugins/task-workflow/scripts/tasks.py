#!/usr/bin/env python3
"""
tasks.py - Main CLI for task management

Usage:
    tasks.py add <title> [options]
    tasks.py list [filters]
    tasks.py list blockers <id>
    tasks.py update <id> [options]
    tasks.py archive [options]
    tasks.py cache init [options]
    tasks.py cache refresh [options]
    tasks.py file create --path <path>

Examples:
    tasks.py add "Fix bug in parser" --due tomorrow --estimate 2h
    tasks.py list --due today --atomic
    tasks.py list blockers abc123
    tasks.py update abc123 --status done
    tasks.py archive --older-than 30
    tasks.py --vault ~/my-brain cache init
    tasks.py file create --path ./efforts/project/TASKS.md
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from archive import archive_tasks, ensure_fresh
from cache import JSONTaskCache, TASKS_FILE_NAMES
from models import Task, format_checkbox_state, format_task, format_tags
from parser import write_file
from utils import generate_task_id, parse_date, parse_duration

EFFORTS_CACHE_FILE = Path.home() / ".cache" / "efforts" / "efforts.json"
DEFAULT_CACHE_FILE = Path.home() / ".cache" / "task-workflow" / "cache.json"
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "assets" / "templates"
TASKS_TEMPLATE = TEMPLATE_DIR / "tasks.template.md"


# --- helpers ---

def _cwd_is_in_efforts(cwd: Path, vault: Path) -> bool:
    """Check if cwd is within the vault's efforts/ directory."""
    if vault is None:
        return False
    try:
        cwd.resolve().relative_to((vault / "efforts").resolve())
        return True
    except ValueError:
        return False


def resolve_current_effort() -> Path | None:
    """
    Resolve the current effort focus, if set, to use as a starting point
    """
    if not EFFORTS_CACHE_FILE.exists():
        return None
    return json.loads(EFFORTS_CACHE_FILE.read_text()).get('focus', None)

def resolve_tasks_file(cwd: Path = None, vault: Path = None) -> Path | None:
    """
    Find the nearest TASKS.md by walking up from cwd.

    Stops at the vault root if provided, otherwise walks to filesystem root.
    If cwd is already inside an effort directory, trusts cwd directly.
    Only consults the effort cache if cwd is NOT inside an effort directory.

    Args:
        cwd: Starting directory (default: current directory)
        vault: Vault root (stop boundary)

    Returns:
        Path to TASKS.md, or None if not found
    """
    current = (cwd or Path.cwd()).resolve()

    # Only consult the effort cache if cwd is NOT already inside efforts/
    if not _cwd_is_in_efforts(current, vault):
        effort = resolve_current_effort()
        if effort is not None:
            current = vault / "efforts" / effort

    while True:
        for name in TASKS_FILE_NAMES:
            candidate = current / name
            if candidate.exists():
                return candidate
        if vault and current == vault:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _unblock_dependents(cache, completed_id: str) -> list[Task]:
    """
    Remove completed_id from all blocked-by lists across the cache.

    Writes affected files and updates the cache.

    Returns:
        List of tasks that became fully unblocked.
    """
    unblocked = []
    affected_files = set()

    # TODO: I feel this is inefficient
    for tid in cache.get_all_task_ids():
        task = cache.find_task(tid)
        if task and completed_id in task.blocking_ids:
            task.remove_blocker(completed_id)
            file_path = cache.find_file(tid)
            if file_path:
                affected_files.add(file_path)
            if not task.is_blocked:
                unblocked.append(task)

    # Write all affected files back
    for fp in affected_files:
        fm = cache.get_frontmatter(fp)
        tree = cache.get_tree(fp)
        write_file(fp, fm, tree)
        cache.update_file(fp, tree, fm)

    return unblocked


# --- add ---

def add_task(args):
    """Add a new task to TASKS.md."""
    cache = args.cache

    target_file = Path(args.file) if args.file else resolve_tasks_file(vault=args.vault)
    if not target_file or not target_file.exists():
        print("Error: No TASKS.md found. Provide --file or run from a directory with TASKS.md.")
        sys.exit(1)

    frontmatter, tree = ensure_fresh(cache, target_file)

    # Generate collision-free ID
    task_id = None
    for _ in range(10):
        candidate = generate_task_id()
        if cache.find_task(candidate) is None:
            task_id = candidate
            break
    if not task_id:
        print("Error: Could not generate unique task ID after 10 attempts.")
        sys.exit(1)

    tags = {
        'id': task_id,
        'created': datetime.now().date().isoformat(),
    }

    if args.due:
        due = parse_date(args.due)
        if due:
            tags['due'] = due
        else:
            print(f"Warning: Could not parse due date '{args.due}', skipping.")
    
    if args.scheduled:
        scheduled = parse_date(args.scheduled)
        if scheduled:
            tags['scheduled'] = scheduled
        else:
            print(f"Warning: Could not parse scheduled date '{args.scheduled}', skipping.")

    if args.estimate:
        est = parse_duration(args.estimate)
        if est:
            tags['estimate'] = est
        else:
            print(f"Warning: Could not parse estimate '{args.estimate}', skipping.")

    if args.blocked_by:
        tags['b'] = args.blocked_by

    if not args.atomic:
        tags['stub'] = ''

    section = args.section
    if section is None and tree.tasks:
        section = tree.tasks[0].section

    new_task = Task(
        title=args.title,
        id=task_id,
        status='open',
        tags=tags,
        notes=[args.notes] if args.notes else [],
        section=section,
    )

    if args.parent:
        parent = tree.find_by_id(args.parent)
        if not parent:
            print(f"Error: Parent task '{args.parent}' not found.")
            sys.exit(1)
        parent.tags.pop('stub', None)
        new_task.indent_level = parent.indent_level + 1
        new_task.section = parent.section
        parent.children.append(new_task)
    else:
        tree.tasks.append(new_task)

    write_file(target_file, frontmatter, tree)
    cache.update_file(target_file, tree, frontmatter)

    print(f"Added: {args.title}")
    print(f"  ID: {task_id}")
    print(f"  File: {target_file}")
    if 'due' in tags:
        print(f"  Due: {tags['due']}")
    if 'scheduled' in tags:
        print(f"  Scheduled: {tags['scheduled']}")
    if args.parent:
        print(f"  Parent: {args.parent}")


# --- list ---

def _filter_time(filter_string, today, date_str) -> bool:
    if not filteR_string:
        return True
    if not date_str:
        return False
    date = datetime.fromisoformat(scheduled_str).date()
    if filter_string == 'today' and date > today:
        return False
    elif filter_string == 'this-week' and not (0 <= (date - today).days <= 7):
        return False
    elif filter_string == 'overdue' and date >= today:
        return False
    return True

def _filter_task(t, args, today, tag_name, tag_value, section_lower):
    """Return True if task passes all active filters."""
    if args.status and t.status != args.status:
        return False
    if args.blocked and not t.is_blocked:
        return False
    if args.stub and not t.is_stub:
        return False
    if section_lower and (not t.section or t.section.lower() != section_lower):
        return False
    if tag_name:
        if tag_value is not None:
            if tag_name not in t.tags or t.tags[tag_name] != tag_value:
                return False
        elif tag_name not in t.tags:
            return False
    try:
        if not _filter_time(args.due, today, t.tags.get('due')):
            return False
        if not _filter_time(args.scheduled, today, t.tags.get('scheduled', None)):
            return False
    except ValueError:
        return False
    return True


def _list_tree(tree, args, today, tag_name, tag_value, section_lower):
    """Filter and print tasks from a single tree."""
    candidates = tree.tasks if not args.atomic else [t for t in tree.all_tasks() if t.is_leaf]
    tasks = [t for t in candidates if _filter_task(t, args, today, tag_name, tag_value, section_lower)]

    if not tasks:
        return 0

    print(f"{tree.file_path}")
    for task in tasks:
        print(f"  {format_task(task, task.indent_level, mode='short')}")
    print()
    return len(tasks)


def list_tasks(args):
    """List tasks with optional filtering."""
    cache = args.cache

    if args.show_all:
        trees = cache.all_trees()
    else:
        target_file = Path(args.file) if args.file else resolve_tasks_file(vault=args.vault)
        if not target_file or not target_file.exists():
            print("Error: No TASKS.md found.")
            sys.exit(1)
        trees = [cache.get_tree(target_file)]

    # Pre-compute filter parameters
    today = datetime.now().date() if args.due else None
    if args.tag and ':' in args.tag:
        tag_name, tag_value = args.tag.split(':', 1)
    else:
        tag_name, tag_value = args.tag, None
    section_lower = args.section.lower() if args.section else None

    total = 0
    for tree in trees:
        total += _list_tree(tree, args, today, tag_name, tag_value, section_lower)

    if total == 0:
        print("No tasks found matching filters.")
    else:
        print(f"{total} task(s) found.")

def list_blockers(args):
    """Show blocking dependencies for a task."""
    cache = args.cache

    task = cache.find_task(args.id)
    if not task:
        print(f"Error: Task '{args.id}' not found in cache.")
        sys.exit(1)

    # Upstream: what blocks this task
    if task.is_blocked:
        print(f"{task.title} ({args.id}) is blocked by:\n")
        for blocker_id in task.blocking_ids:
            blocker = cache.find_task(blocker_id)
            if blocker:
                checkbox = format_checkbox_state(blocker.status)
                print(f"  - {checkbox} {blocker.title} ({blocker_id})")
            else:
                print(f"  - {blocker_id} (not found in cache)")
    else:
        print(f"{task.title} ({args.id}) has no blockers.")

    # Downstream: what this task blocks
    blocks = []
    for tid in cache.get_all_task_ids():
        other = cache.find_task(tid)
        if other and args.id in other.blocking_ids:
            blocks.append(other)

    if blocks:
        print(f"\nBlocks {len(blocks)} task(s):\n")
        for t in blocks:
            print(f"  - {t.title} ({t.id})")


# --- update ---

def update_task(args):
    """Update a task's metadata, with knock-on effects for completion."""
    cache = args.cache

    task = cache.find_task(args.id)
    if not task:
        print(f"Error: Task '{args.id}' not found.")
        sys.exit(1)

    file_path = cache.find_file(args.id)
    ensure_fresh(cache, file_path)

    # Re-fetch after ensure_fresh (tree may have been replaced if stale)
    task = cache.find_task(args.id)
    frontmatter = cache.get_frontmatter(file_path)
    tree = cache.get_tree(file_path)

    updated = False
    unblocked = []

    # Status change
    if args.status and args.status != task.status:
        task.status = args.status
        updated = True
        if args.status == "done":
            task.tags['completed'] = datetime.now().date().isoformat()
            unblocked = _unblock_dependents(cache, args.id)

    # Metadata updates
    if args.due:
        due = parse_date(args.due)
        if due:
            task.tags['due'] = due
            updated = True
        else:
            print(f"Warning: Could not parse due date '{args.due}', skipping.")

    if args.scheduled:
        scheduled = parse_date(args.scheduled)
        if scheduled:
            tags['scheduled'] = scheduled
            updated = True
        else:
            print(f"Warning: Could not parse scheduled date '{args.scheduled}', skipping.")

    if args.estimate:
        est = parse_duration(args.estimate)
        if est:
            task.tags['estimate'] = est
            updated = True
        else:
            print(f"Warning: Could not parse estimate '{args.estimate}', skipping.")

    if args.blocked_by:
        task.add_blocker(args.blocked_by)
        updated = True

    if args.unblock:
        task.remove_blocker(args.unblock)
        updated = True

    if args.notes is not None:
        task.notes = [args.notes] if args.notes else []
        updated = True

    if args.title:
        task.title = args.title
        updated = True

    if args.atomic:
        if 'stub' in task.tags:
            del task.tags['stub']
            updated = True

    if not updated:
        print("No changes made.")
        return

    # Write task's file
    write_file(file_path, frontmatter, tree)
    cache.update_file(file_path, tree, frontmatter)

    print(f"Updated: {task.title} ({args.id})")
    if args.status == "done":
        print(f"  Completed: {task.tags.get('completed')}")
    if unblocked:
        print(f"  Unblocked {len(unblocked)} task(s):")
        for t in unblocked:
            print(f"    - {t.title} ({t.id})")


# --- archive ---

def archive_cmd(args):
    """Archive old completed tasks."""
    cache = args.cache

    target_file = Path(args.file) if args.file else resolve_tasks_file(vault=args.vault)
    if not target_file:
        print("Error: No TASKS.md found.")
        sys.exit(1)

    archive_file = target_file.parent / "TASKS-ARCHIVE.md"
    result = archive_tasks(cache, target_file, archive_file, args.older_than, args.dry_run)

    if result["status"] == "error":
        print(f"Error: {result['message']}")
        sys.exit(1)

    if args.dry_run and result["count"] > 0:
        print(f"Dry run: {result['count']} task(s) would be archived:")
        for task in result.get("tasks", []):
            print(f"  - {task.title}")
    elif result["count"] > 0:
        print(f"Archived {result['count']} task(s) to {archive_file}")
    else:
        print("No tasks to archive.")


# --- cache ---

def cache_init(args):
    """Initialize the cache by scanning the vault."""
    cache = args.cache
    vault = args.vault

    count = cache.scan_vault(vault, exclude_dirs=args.exclude)
    ids = cache.get_all_task_ids()
    print(f"Cache initialized: {count} file(s) loaded, {len(ids)} task(s) indexed.")


def cache_refresh(args):
    """Clear and rebuild the cache."""
    cache = args.cache
    vault = args.vault

    cache.clear()
    count = cache.scan_vault(vault, exclude_dirs=args.exclude)
    ids = cache.get_all_task_ids()
    print(f"Cache refreshed: {count} file(s) loaded, {len(ids)} task(s) indexed.")


# --- file ---

def file_create(args):
    """Create a new TASKS.md from the template."""
    target = Path(args.path)

    # If path is a directory (or has no suffix), create TASKS.md inside it
    if target.is_dir() or not target.suffix:
        target = target / "TASKS.md"

    if target.exists() and not args.force:
        print(f"Error: {target} already exists. Use --force to overwrite.")
        sys.exit(1)

    if not TASKS_TEMPLATE.exists():
        print(f"Error: Template not found: {TASKS_TEMPLATE}")
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)

    content = TASKS_TEMPLATE.read_text(encoding='utf-8')
    content = content.replace('{{DATE_CREATED}}', datetime.now().date().isoformat())
    target.write_text(content, encoding='utf-8')

    print(f"Created: {target}")


# --- main ---

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Task management CLI for TASKS.md files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--vault', default='C:\\Users\\ghoop\\Desktop\\my-brain',
                        help='Vault root directory')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # --- add ---
    add_p = subparsers.add_parser('add', help='Add a new task')
    add_p.add_argument('title', help='Task title')
    add_p.add_argument('--file', help='Path to TASKS.md')
    add_p.add_argument('--due', help='Due date (YYYY-MM-DD, today, tomorrow, friday, etc.)')
    add_p.add_argument('--scheduled', help='Scheduled date (YYYY-MM-DD, today, tomorrow, friday, etc.)')
    add_p.add_argument('--estimate', help='Time estimate (e.g., 2h, 30m, 1d)')
    add_p.add_argument('--blocked-by', help='ID of blocking task')
    add_p.add_argument('--parent', help='ID of parent task (add as subtask)')
    add_p.add_argument('--atomic', action='store_true', help='Mark as atomic (no #stub)')
    add_p.add_argument('--notes', help='Additional notes')
    add_p.add_argument('--section', help='Target section')
    add_p.set_defaults(func=add_task)

    # --- list ---
    list_p = subparsers.add_parser('list', help='List tasks')
    list_p.add_argument('--file', help='Path to TASKS.md')
    list_p.add_argument('--all', action='store_true', dest='show_all',
                        help='Show all tasks including subtasks')
    list_p.add_argument('--atomic', action='store_true', help='Show only leaf tasks')
    list_p.add_argument('--status', choices=['open', 'in-progress', 'done'],
                        help='Filter by status')
    list_p.add_argument('--due', choices=['today', 'this-week', 'overdue'],
                        help='Filter by due date')
    # TODO: might be worth giving better options here
    list_p.add_argument('--scheduled', choices=['today', 'this-week'], help='Set scheduled date')
    list_p.add_argument('--blocked', action='store_true', help='Show only blocked tasks')
    list_p.add_argument('--stub', action='store_true', help='Show only stub tasks')
    list_p.add_argument('--section', help='Filter by section name')
    list_p.add_argument('--tag', help='Filter by tag (name or name:value)')
    list_p.set_defaults(func=list_tasks)

    list_sub = list_p.add_subparsers(dest='list_command')
    blockers_p = list_sub.add_parser('blockers', help='Show blocking dependencies')
    blockers_p.add_argument('id', help='Task ID')
    blockers_p.set_defaults(func=list_blockers)

    # --- update ---
    update_p = subparsers.add_parser('update', help='Update a task')
    update_p.add_argument('id', help='Task ID')
    update_p.add_argument('--status', choices=['open', 'in-progress', 'done'],
                          help='Change status')
    update_p.add_argument('--due', help='Set due date')
    update_p.add_argument('--scheduled', help='Set scheduled date')
    update_p.add_argument('--estimate', help='Set time estimate')
    update_p.add_argument('--blocked-by', help='Add blocking dependency')
    update_p.add_argument('--unblock', help='Remove blocking dependency')
    update_p.add_argument('--notes', help='Set notes (empty string to clear)')
    update_p.add_argument('--title', help='Change title')
    update_p.add_argument('--atomic', action='store_true', help='Remove #stub tag')
    update_p.set_defaults(func=update_task)

    # --- archive ---
    archive_p = subparsers.add_parser('archive', help='Archive completed tasks')
    archive_p.add_argument('--file', help='Path to TASKS.md')
    archive_p.add_argument('--older-than', type=int, default=30,
                           help='Days since completion (default: 30)')
    archive_p.add_argument('--dry-run', action='store_true',
                           help='Preview without modifying')
    archive_p.set_defaults(func=archive_cmd)

    # --- cache ---
    cache_p = subparsers.add_parser('cache', help='Manage task cache')
    cache_sub = cache_p.add_subparsers(dest='cache_command', required=True)

    init_p = cache_sub.add_parser('init', help='Initialize cache from vault')
    init_p.add_argument('--exclude', nargs='*', default=[], help='Directories to skip')
    init_p.set_defaults(func=cache_init)

    refresh_p = cache_sub.add_parser('refresh', help='Clear and rebuild cache')
    refresh_p.add_argument('--exclude', nargs='*', default=[], help='Directories to skip')
    refresh_p.set_defaults(func=cache_refresh)

    # --- file ---
    file_p = subparsers.add_parser('file', help='Manage task files')
    file_sub = file_p.add_subparsers(dest='file_command', required=True)

    create_p = file_sub.add_parser('create', help='Create TASKS.md from template')
    create_p.add_argument('--path', required=True, help='Target path (file or directory)')
    create_p.add_argument('--force', action='store_true', help='Overwrite existing file')
    create_p.set_defaults(func=file_create)

    # Parse and dispatch
    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    args.vault = Path(args.vault).resolve()
    if not args.vault.is_dir():
        print(f"Error: Vault directory not found: {args.vault}")
        sys.exit(1)

    args.cache = JSONTaskCache(DEFAULT_CACHE_FILE)
    args.func(args)


if __name__ == '__main__':
    main()
