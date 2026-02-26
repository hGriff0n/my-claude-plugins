"""
Effort data models.

An "effort" is a project workspace directory identified by the presence of
a CLAUDE.md marker file. Efforts live under $VAULT_ROOT/efforts/ and are
classified as active (top-level) or backlog (under __backlog/).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class EffortStatus(str, Enum):
    ACTIVE = "active"
    BACKLOG = "backlog"


@dataclass
class Effort:
    """
    Represents a single effort (project workspace) discovered in the vault.
    """

    name: str
    path: Path
    status: EffortStatus
    is_focused: bool = False
    tasks_file: Optional[Path] = None

    @property
    def display_status(self) -> str:
        """Human-readable status including focus indicator."""
        if self.is_focused:
            return f"{self.status.value} (focused)"
        return self.status.value
