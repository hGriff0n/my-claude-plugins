"""
Core task data models.

The Task model captures all semantic information needed to reconstruct the
original markdown task line via utils.formatting. No raw line storage is used —
the model IS the source of truth, and formatting.py defines the canonical
rendering format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional


@dataclass
class Task:
    """
    A single task item parsed from a TASKS.md file.

    All information needed to reconstruct the original markdown line is
    captured here. The canonical rendering is defined in utils.formatting.
    """

    title: str
    id: Optional[str] = None
    status: Literal["open", "in-progress", "done"] = "open"
    tags: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    children: List[Task] = field(default_factory=list)
    indent_level: int = 0
    line_number: int = 0
    section: Optional[str] = None
    section_level: int = 0
    file_path: Optional[Path] = None

    @property
    def ref(self) -> Optional[str]:
        """Obsidian task reference in 'path:line' format, or None if unavailable."""
        if self.file_path:
            return f"{self.file_path.as_posix()}:{self.line_number}"
        return None

    @property
    def is_stub(self) -> bool:
        """True if task is marked as a stub (placeholder for subtasks)."""
        return "stub" in self.tags

    @property
    def is_blocked(self) -> bool:
        """True if task has unresolved blocking dependencies."""
        return "blocked" in self.tags

    @property
    def blocking_ids(self) -> List[str]:
        """List of task IDs that block this task."""
        value = self.tags.get("blocked", "")
        return [tid.strip() for tid in value.split(",") if tid.strip()] if value else []

    def add_blocker(self, blocker_id: str) -> None:
        """Add a blocker ID to this task's blocked list."""
        ids = self.blocking_ids
        if blocker_id not in ids:
            ids.append(blocker_id)
        self.tags["blocked"] = ",".join(ids)

    def remove_blocker(self, blocker_id: str) -> None:
        """Remove a blocker ID from this task's blocked list."""
        ids = [i for i in self.blocking_ids if i != blocker_id]
        if ids:
            self.tags["blocked"] = ",".join(ids)
        else:
            self.tags.pop("blocked", None)

    def all_tasks(self) -> List[Task]:
        """Return this task and all descendants as a flat list."""
        result = [self]
        for child in self.children:
            result.extend(child.all_tasks())
        return result


@dataclass
class SectionBlock:
    """
    A section heading and the root tasks beneath it.

    Preserves the structural order of sections in the original file.
    """

    heading: str
    level: int
    tasks: List[Task] = field(default_factory=list)


@dataclass
class TaskTree:
    """
    Represents a fully parsed TASKS.md file.

    Sections preserve the original heading order, enabling exact file
    reconstruction via the serializer in task_parser.py.
    """

    file_path: Path
    sections: List[SectionBlock] = field(default_factory=list)
    frontmatter_lines: List[str] = field(default_factory=list)

    def all_tasks(self) -> List[Task]:
        """Return all tasks across all sections as a flat list."""
        result = []
        for section in self.sections:
            for task in section.tasks:
                result.extend(task.all_tasks())
        return result

    def find_by_id(self, task_id: str) -> Optional[Task]:
        """Find a task by its ID."""
        for task in self.all_tasks():
            if task.id == task_id:
                return task
        return None

    def find_section(self, heading: str) -> Optional[SectionBlock]:
        """Find a section block by its heading text."""
        for section in self.sections:
            if section.heading == heading:
                return section
        return None


@dataclass
class CachedFile:
    """A parsed task file held in the vault cache."""

    file_path: Path
    tree: TaskTree
    mtime: float
