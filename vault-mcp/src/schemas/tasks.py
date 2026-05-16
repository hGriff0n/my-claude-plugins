from datetime import date
from enum import Enum
from pathlib import Path
from typing import List

from pydantic import BaseModel

from schemas.time import TimeBlock


# Milestones are tasks internally but aren't stored as such in obsidian.
# TASKFILE is an ephemeral wrapper for whole-file rendering — it is not
# persisted to the database.
class TaskType(str, Enum):
    MILESTONE = "MILESTONE"
    TASK = "TASK"
    TASKFILE = "TASKFILE"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"


class Dependencies(BaseModel):
    blocked: List[str]  # Task ids of blocking tasks
    parent: str  # Task id of parent task
    children: List[str]  # Task ids of child tasks (B = A.parent <=> A in B.children)


class Note(BaseModel):
    indent: int  # Indent level relative to the parent task (0 = directly under)
    text: str  # Bullet text, leading "- " stripped


class Task(BaseModel):
    """A single task
    """
    id: str  # A hexadecimal id that is internally generated to each task
    type: TaskType  # The "type" of the task, mostly used for differentiating milestone tasks when writing/reading from taskfiles
    status: TaskStatus  # Whether the task is open/closed/blocked/etc
    text: str  # The task "title" line
    effort: str  # The parent effort this task belongs to (or 'none' if in the root taskfile)
    file_order: int = -1  # 0-based line index in source file at last parse; -1 if not yet on disk
    estimate: str = ""  # Estimated effort/duration (e.g. "2h", "30m"); empty if unset
    actual: str = ""  # Recorded actual effort/duration; empty if unset
    notes: List[Note]  # Bullet points attached to this task (indent relative to parent)
    tags: List[str]  # Tags/properties that are specially parsed from the taskline
    dependencies: Dependencies  # References to other tasks. Handles both parent-child and blocking relations
    time_details: TimeBlock  # A collection of various time properties, notably `created` and `last_updated`
