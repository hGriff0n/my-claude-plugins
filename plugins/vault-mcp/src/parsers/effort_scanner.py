"""
Effort directory scanner.

Adapted from effort-workflow/scripts/state_manager.py.

An "effort" is any directory that contains a CLAUDE.md marker file.
Efforts live under $VAULT_ROOT/efforts/:
  - Active: top-level directories directly under efforts/ with CLAUDE.md
  - Backlog: directories anywhere under efforts/__backlog/ with CLAUDE.md

Directory names to skip at top level: __ideas, dashboard.base
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from models.effort import Effort, EffortStatus

# Task files associated with an effort (checked by name, not path)
from parsers.task_parser import TASK_FILE_NAMES

# Top-level names to ignore during scanning
_SKIP_NAMES: Set[str] = {"__ideas", "dashboard.base"}

# The special backlog subdirectory name
_BACKLOG_DIR = "__backlog"


def is_effort_dir(path: Path) -> bool:
    """Return True if path is a directory containing a CLAUDE.md marker."""
    return path.is_dir() and (path / "CLAUDE.md").exists()


def _find_tasks_file(effort_path: Path) -> Optional[Path]:
    """Return the path to the tasks file inside an effort dir, if present."""
    for name in TASK_FILE_NAMES:
        candidate = effort_path / name
        if candidate.exists():
            return candidate
    return None


def _scan_backlog_dir(backlog_path: Path) -> List[Effort]:
    """
    Recursively scan a __backlog directory for effort subdirectories.

    Any directory with a CLAUDE.md file anywhere under __backlog/ is
    considered a backlog effort.
    """
    efforts: List[Effort] = []
    if not backlog_path.is_dir():
        return efforts

    for child in sorted(backlog_path.iterdir()):
        if not child.is_dir():
            continue
        if is_effort_dir(child):
            efforts.append(
                Effort(
                    name=child.name,
                    path=child,
                    status=EffortStatus.BACKLOG,
                    tasks_file=_find_tasks_file(child),
                )
            )
        else:
            # Recurse into subdirectories (nested backlog)
            efforts.extend(_scan_backlog_dir(child))

    return efforts


def scan_efforts(efforts_root: Path) -> Dict[str, Effort]:
    """
    Scan the efforts directory and return all discovered efforts.

    Args:
        efforts_root: Path to $VAULT_ROOT/efforts/

    Returns:
        Dict mapping effort name → Effort (focus state is not set here;
        the cache layer manages focus separately).
    """
    result: Dict[str, Effort] = {}

    if not efforts_root.is_dir():
        return result

    for child in sorted(efforts_root.iterdir()):
        if child.name in _SKIP_NAMES:
            continue

        if child.name == _BACKLOG_DIR:
            for effort in _scan_backlog_dir(child):
                result[effort.name] = effort
        elif is_effort_dir(child):
            result[child.name] = Effort(
                name=child.name,
                path=child,
                status=EffortStatus.ACTIVE,
                tasks_file=_find_tasks_file(child),
            )
        # Directories without CLAUDE.md are not efforts — skip silently

    return result
