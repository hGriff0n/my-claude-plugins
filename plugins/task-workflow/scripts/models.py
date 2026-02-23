#!/usr/bin/env python3
"""
Core data models for task trees.

These dataclasses are used throughout the task-workflow system to represent
tasks and their hierarchical structure.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional


# Tag to emoji mappings (Obsidian Tasks plugin compatibility)
TAG_TO_EMOJI = {
    'id': '🆔',
    'b': '⛔',
    'created': '➕',
    'due': '📅',
    'completed': '✅',
    'scheduled': '⏳'
}


# Helper functions for blocked list manipulation

def parse_blocked_list(blocked_value: str) -> List[str]:
    """
    Parse a comma-separated list of blocking task IDs.

    Args:
        blocked_value: Value of #b: or ⛔ tag (e.g., "abc123,def456")

    Returns:
        List of task IDs
    """
    if not blocked_value:
        return []

    return [tid.strip() for tid in blocked_value.split(',') if tid.strip()]


def format_blocked_list(task_ids: List[str]) -> str:
    """
    Format a list of task IDs into comma-separated string.

    Args:
        task_ids: List of task IDs

    Returns:
        Comma-separated string
    """
    return ",".join(task_ids)


@dataclass
class Task:
    """Represents a single task in the tree."""

    title: str
    id: Optional[str] = None
    status: Literal["open", "in-progress", "done"] = "open"
    tags: dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    children: List['Task'] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)
    indent_level: int = 0
    line_number: int = 0
    section: Optional[str] = None  # Track which section this task belongs to
    section_level: int = 0  # Heading level of the section (0 = no heading, 3 = ###, 4 = ####, etc.)

    @property
    def is_leaf(self) -> bool:
        """True if task has no children (atomic task)."""
        return len(self.children) == 0

    @property
    def is_stub(self) -> bool:
        """True if task is marked as a stub."""
        return 'stub' in self.tags

    @property
    def is_blocked(self) -> bool:
        """True if task has blocking dependencies."""
        return 'b' in self.tags or 'blocked' in self.tags

    @property
    def blocking_ids(self) -> List[str]:
        """List of task IDs that block this task."""
        blocked_value = self.tags.get('b', self.tags.get('blocked', ''))
        return parse_blocked_list(blocked_value)

    def add_blocker(self, blocker_id: str) -> None:
        """
        Add a blocker ID to this task's blocked list.

        Args:
            blocker_id: ID of the blocking task
        """
        blocked_ids = self.blocking_ids

        # Add new blocker if not already present
        if blocker_id not in blocked_ids:
            blocked_ids.append(blocker_id)

        # Update the tag
        self.tags['b'] = format_blocked_list(blocked_ids)

    def remove_blocker(self, blocker_id: str) -> None:
        """
        Remove a blocker ID from this task's blocked list.

        Args:
            blocker_id: ID of the blocking task to remove
        """
        blocked_ids = self.blocking_ids

        # Remove blocker if present
        if blocker_id in blocked_ids:
            blocked_ids.remove(blocker_id)

        # Update or remove the tag
        if blocked_ids:
            self.tags['b'] = format_blocked_list(blocked_ids)
        else:
            self.tags.pop('b', None)
            self.tags.pop('blocked', None)  # Also remove alias

    def __str__(self) -> str:
        """Format task as markdown string."""
        return format_task(self)


@dataclass
class TaskTree:
    """Represents a parsed TASKS.md file."""

    tasks: List[Task]
    file_path: Optional[Path] = None

    def all_tasks(self) -> List[Task]:
        """Get all tasks (including nested children) as a flat list."""
        def flatten(task: Task) -> List[Task]:
            result = [task]
            for child in task.children:
                result.extend(flatten(child))
            return result

        all_items = []
        for task in self.tasks:
            all_items.extend(flatten(task))
        return all_items

    def find_by_id(self, task_id: str) -> Optional[Task]:
        """Find a task by its ID."""
        for task in self.all_tasks():
            if task.id == task_id:
                return task
        return None

    def find_by_title(self, title_query: str) -> List[Task]:
        """Find tasks by fuzzy title match."""
        query_lower = title_query.lower()
        matches = []
        for task in self.all_tasks():
            if query_lower in task.title.lower():
                matches.append(task)
        return matches

    def __str__(self) -> str:
        """Format task tree as markdown string."""
        return format_tree(self)


# Formatting functions

def format_checkbox_state(status: Literal["open", "in-progress", "done"]) -> str:
    """
    Format status as checkbox markdown.

    Args:
        status: Task status

    Returns:
        Checkbox string (e.g., "[ ]", "[/]", "[x]")
    """
    if status == "done":
        return "[x]"
    elif status == "in-progress":
        return "[/]"
    else:
        return "[ ]"


def format_tag(tag_name: str, value: str) -> str:
    """
    Format a tag in the preferred format (emoji if available, else #tag:value).

    Args:
        tag_name: Tag name (e.g., "id", "due")
        value: Tag value (e.g., "a7f3c2", "2026-02-15")

    Returns:
        Formatted tag string
    """
    # Check if emoji equivalent exists
    if tag_name in TAG_TO_EMOJI:
        emoji = TAG_TO_EMOJI[tag_name]
        return f"{emoji} {value}"

    # Use #tag:value format
    if value:
        return f"#{tag_name}:{value}"
    else:
        return f"#{tag_name}"


def format_tags(tags: Dict[str, str]) -> str:
    """
    Format multiple tags into a space-separated string.

    Priority order: id, created, due, completed, blocked, estimate, actual, stub, routine

    Args:
        tags: Dict of tag names to values

    Returns:
        Space-separated formatted tags
    """
    priority_order = ['id', 'created', 'due', 'completed', 'b', 'blocked', 'estimate', 'actual', 'stub', 'routine']

    formatted = []

    # Add tags in priority order
    for tag_name in priority_order:
        if tag_name in tags:
            formatted.append(format_tag(tag_name, tags[tag_name]))

    # Add any remaining tags not in priority order
    for tag_name, value in tags.items():
        if tag_name not in priority_order:
            formatted.append(format_tag(tag_name, value))

    return " ".join(formatted)


def format_task(
    task: Task,
    indent_level: int = 0,
    mode: Literal['short', 'long', 'full'] = 'full',
) -> str:
    """
    Format a task back into markdown.

    Args:
        task: Task to format
        indent_level: Indentation level (for subtasks)
        mode: Output detail level
            - short: task line only (checkbox + title + tags)
            - long:  task line + notes
            - full:  task line + notes + children (recursive)

    Returns:
        Markdown string
    """
    indent = "    "  # 4 spaces per level
    full_indent = indent * indent_level
    checkbox = format_checkbox_state(task.status)

    # Build task line
    if task.tags:
        task_line = f"{full_indent}- {checkbox} {task.title} {format_tags(task.tags)}"
    else:
        task_line = f"{full_indent}- {checkbox} {task.title}"

    if mode == 'short':
        return task_line

    lines = [task_line]

    # Add notes
    for note in task.notes:
        lines.append(f"{full_indent}{indent}- {note}")

    if mode == 'long':
        return "\n".join(lines)

    # Add children (full mode)
    for child in task.children:
        lines.append(format_task(child, indent_level + 1, mode='full'))

    return "\n".join(lines)

def format_tree(tree: TaskTree) -> str:
    """
    Format a tree back into markdown.

    Args:
        tree: TaskTree to format

    Returns:
        Markdown string
    """
    return '\n'.join(format_task(task) for task in tree.tasks)