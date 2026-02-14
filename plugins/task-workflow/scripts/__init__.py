#!/usr/bin/env python3
"""
Task workflow parser - refactored version.

Main API:
    from scripts.new import parse_file, write_file, Task, TaskTree

    # Parse a file
    frontmatter, tree = parse_file(Path("TASKS.md"))

    # Modify tasks
    task = tree.find_by_id("abc123")
    task.status = "done"

    # Write back
    write_file(Path("TASKS.md"), frontmatter, tree)
"""

from .models import (
    Task,
    TaskTree,
    format_task,
    format_checkbox_state,
    format_tree,
    format_tag,
    format_tags,
    parse_blocked_list,
    format_blocked_list,
)
from .parser import (
    parse_file,
    write_file,
    parse_content,
    parse_task_line,
    parse_heading_line,
    parse_checkbox_state,
    calculate_indent_level,
    split_tags,
)
from .cache import (
    TaskCacheInterface,
    JSONTaskCache,
    create_cache,
)

__all__ = [
    # Models
    'Task',
    'TaskTree',
    # Main API
    'parse_file',
    'write_file',
    # Formatting
    'format_task',
    'format_checkbox_state',
    'format_tree',
    'format_tag',
    'format_tags',
    # Cache
    'TaskCacheInterface',
    'JSONTaskCache',
    'create_cache',
    # Utilities
    'parse_content',
    'parse_task_line',
    'parse_heading_line',
    'parse_checkbox_state',
    'calculate_indent_level',
    'split_tags',
    'parse_blocked_list',
    'format_blocked_list',
]
