"""Parser protocol — see `specs/arch/parser.md`."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import List, Protocol


class Parser[ItemType, UpdateTypes](Protocol):
    @abstractmethod
    def initialize(self, db, watcher) -> None:
        """One-time setup: register initial watchers.

        Initial watcher registrations fire immediately on existing matching
        state; those firings call `parse(...)` and seed the database. Table
        registration is performed externally by the server before this call.
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, file: Path) -> List[ItemType]:
        """Convert a file or folder into schema instances.

        May register additional watchers as new files/folders are discovered.
        """
        raise NotImplementedError

    @abstractmethod
    def update(self, elem: ItemType, op: UpdateTypes) -> None:
        """Apply a write operation to the database (no file I/O)."""
        raise NotImplementedError
