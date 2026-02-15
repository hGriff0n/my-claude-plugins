#!/usr/bin/env python3
"""
upgrade.py - Upgrade task files to ensure proper metadata and formatting

Usage:
    upgrade.py <file_path> [options]

Examples:
    upgrade.py TASKS.md
    upgrade.py TASKS.md --dry-run
    upgrade.py TASKS.md --use-default-date 2024-01-01

This script will:
- Auto-generate IDs for tasks without them
- Add 'created' dates using file's 'last updated' from frontmatter
- Ensure all tasks are properly formatted
- Preserve all existing metadata
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cache import JSONTaskCache
from models import Task
from parser import parse_file, write_file
from utils import generate_task_id


def extract_last_updated_date(frontmatter_lines: list[str]) -> str | None:
    """
    Extract the 'last updated' date from frontmatter.

    Args:
        frontmatter_lines: List of frontmatter lines

    Returns:
        ISO date string or None if not found
    """
    for line in frontmatter_lines:
        # Match "last updated: YYYY-MM-DD" or "last updated: YYYY-MM-DDTHH:MM:SS"
        if line.strip().startswith('last updated:'):
            date_str = line.split(':', 1)[1].strip()
            # Try to parse as ISO date
            try:
                # Handle both date and datetime formats
                if 'T' in date_str:
                    parsed = datetime.fromisoformat(date_str).date()
                else:
                    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
                return parsed.isoformat()
            except ValueError:
                pass
    return None


def upgrade_task(task: Task, default_created_date: str, existing_ids: set[str]) -> bool:
    """
    Upgrade a single task with missing metadata.

    Args:
        task: Task to upgrade
        default_created_date: Default date to use for 'created' tag
        existing_ids: Set of existing task IDs (to avoid collisions)

    Returns:
        True if task was modified, False otherwise
    """
    modified = False

    # Generate ID if missing
    if not task.id or 'id' not in task.tags:
        # Generate collision-free ID
        for _ in range(10):
            candidate = generate_task_id()
            if candidate not in existing_ids:
                task.id = candidate
                task.tags['id'] = candidate
                existing_ids.add(candidate)
                modified = True
                break
    else:
        existing_ids.add(task.id)

    # Add 'created' date if missing
    if 'created' not in task.tags:
        task.tags['created'] = default_created_date
        modified = True

    # Recursively upgrade children
    for child in task.children:
        if upgrade_task(child, default_created_date, existing_ids):
            modified = True

    return modified


def upgrade_file(file_path: Path, default_date: str | None = None, dry_run: bool = False) -> dict:
    """
    Upgrade a task file with proper metadata and formatting.

    Args:
        file_path: Path to the task file
        default_date: Default date to use for 'created' (overrides frontmatter)
        dry_run: If True, don't write changes to file

    Returns:
        Dict with upgrade results
    """
    if not file_path.exists():
        return {
            "status": "error",
            "message": f"File not found: {file_path}"
        }

    # Parse the file
    frontmatter_lines, tree = parse_file(file_path)

    # Determine default created date
    created_date = default_date
    if not created_date:
        # Try to extract from frontmatter
        created_date = extract_last_updated_date(frontmatter_lines)

    if not created_date:
        # Fall back to today's date
        created_date = datetime.now().date().isoformat()

    # Track existing IDs to avoid collisions
    existing_ids = set()

    # Upgrade all tasks
    total_modified = 0
    modified_tasks = []

    for task in tree.tasks:
        if upgrade_task(task, created_date, existing_ids):
            total_modified += 1
            modified_tasks.append(task)

    # Count all tasks (including children)
    all_tasks = tree.all_tasks()

    result = {
        "status": "success",
        "file": str(file_path),
        "total_tasks": len(all_tasks),
        "modified_count": total_modified,
        "modified_tasks": modified_tasks,
        "default_created_date": created_date,
        "dry_run": dry_run
    }

    # Write the file if not dry run
    if not dry_run and total_modified > 0:
        write_file(file_path, frontmatter_lines, tree)
        result["written"] = True
    else:
        result["written"] = False

    return result


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Upgrade task files with proper metadata and formatting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('file', type=Path, help='Path to task file (TASKS.md)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without modifying the file')
    parser.add_argument('--use-default-date', dest='default_date',
                        help='Use this date for all created tags (YYYY-MM-DD)')

    args = parser.parse_args()

    # Validate default date if provided
    if args.default_date:
        try:
            datetime.strptime(args.default_date, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid date format '{args.default_date}'. Use YYYY-MM-DD.")
            sys.exit(1)

    # Upgrade the file
    result = upgrade_file(args.file, args.default_date, args.dry_run)

    if result["status"] == "error":
        print(f"Error: {result['message']}")
        sys.exit(1)

    # Print results
    print(f"File: {result['file']}")
    print(f"Total tasks: {result['total_tasks']}")
    print(f"Default created date: {result['default_created_date']}")

    if result['dry_run']:
        print(f"\nDry run: {result['modified_count']} task(s) would be upgraded")
        if result['modified_count'] > 0:
            print("\nTasks that would be modified:")
            for task in result['modified_tasks']:
                changes = []
                if task.id:
                    changes.append(f"ID={task.id}")
                if 'created' in task.tags:
                    changes.append(f"created={task.tags['created']}")
                print(f"  - {task.title} ({', '.join(changes)})")
    else:
        if result['modified_count'] > 0:
            print(f"\nUpgraded {result['modified_count']} task(s)")
            print("File saved successfully!")
        else:
            print("\nNo changes needed - all tasks already have proper metadata")


if __name__ == '__main__':
    main()
