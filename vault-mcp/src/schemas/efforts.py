from datetime import date
from enum import Enum
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

# TODO: claude - this is wrong relative import
from time import TimeBlock


class EffortStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BACKLOG = "BACKLOG"


class TaskStats(BaseModel):
    num_by_status: Dict[str, int]  # number of tasks in each status, keys are TaskStatus enum str values


class DisplayDetails(BaseModel):
    task_stats: TaskStats  # Short summarizations of task numbers such as "completed"/"open"/etc that can be useful for displaying  some things


class Effort(BaseModel):
    """A single effort in my personal vault
    """
    name: str  # The effort's name, the final folder in `path`
    path: Path  # The vault-relative file path
    status: EffortStatus
    description: str  # A short text of the effort goal and purpose
    time_details: TimeBlock  # A collection of various time properties, notably `created` and `last_updated`
    display: DisplayDetails  # A collection of various properties/computations that may be useful for displaying information
