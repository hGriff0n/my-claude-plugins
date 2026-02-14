#!/usr/bin/env python3
"""
Task caching layer for fast cross-file lookups.

Provides an abstract interface for caching task data, with a JSON-based
implementation. Future implementations could use databases (SQLite, Redis, etc.).

The cache is the internal entrypoint for all commands - it sits between
commands and TASKS.md files, avoiding constant parsing/writing while keeping
TASKS.md as the source of truth.
"""

import json
import os
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Set

# Import models from new parser
sys.path.insert(0, str(Path(__file__).parent))
from models import Task, TaskTree

# File names recognized as task files
TASKS_FILE_NAMES = {"TASKS.md", "01 TASKS.md"}


class TaskCacheInterface(ABC):
    """
    Abstract interface for task caching.

    This allows for future migrations to different storage backends
    (SQLite, Redis, PostgreSQL, etc.) without changing command code.
    """

    @abstractmethod
    def is_file_stale(self, file_path: Path) -> bool:
        """
        Check if a file has been modified since last cache.

        Args:
            file_path: Path to TASKS.md file

        Returns:
            True if file needs re-parsing
        """
        pass

    @abstractmethod
    def update_file(self, file_path: Path, tree: TaskTree, frontmatter: Optional[List[str]] = None) -> None:
        """
        Update cache with tasks from a file.

        Args:
            file_path: Path to TASKS.md file
            tree: Parsed TaskTree
            frontmatter: Frontmatter lines (including --- delimiters)
        """
        pass

    @abstractmethod
    def get_tree(self, file_path: Path) -> Optional[TaskTree]:
        """
        Get the cached TaskTree for a file.

        Args:
            file_path: Path to TASKS.md file

        Returns:
            TaskTree or None if not cached
        """
        pass

    @abstractmethod
    def get_frontmatter(self, file_path: Path) -> Optional[List[str]]:
        """
        Get the cached frontmatter for a file.

        Args:
            file_path: Path to TASKS.md file

        Returns:
            Frontmatter lines or None if not cached
        """
        pass

    @abstractmethod
    def find_task(self, task_id: str) -> Optional[Task]:
        """
        Find a task by ID across all cached files.

        Args:
            task_id: Task ID

        Returns:
            Task object or None
        """
        pass

    @abstractmethod
    def find_file(self, task_id: str) -> Optional[Path]:
        """
        Find which file contains a task ID.

        Args:
            task_id: Task ID

        Returns:
            Path to TASKS.md file or None
        """
        pass

    @abstractmethod
    def get_all_task_ids(self) -> List[str]:
        """Get all task IDs in the cache."""
        pass

    @abstractmethod
    def all_trees(self) -> List[TaskTree]:
        """Get all cached TaskTree objects (each with file_path set)."""
        pass

    def scan_vault(self, vault_root: Path, exclude_dirs: List[str] = None) -> int:
        """
        Walk the vault directory tree, find all tasks files, and load them.

        Only re-parses files that are stale (modified since last cache).
        Use clear() first for a full rebuild.

        Args:
            vault_root: Root directory to scan
            exclude_dirs: Directory names to skip (e.g. [".git", ".obsidian"])

        Returns:
            Number of files loaded (parsed or already cached)
        """
        from parser import parse_file

        exclude = set(exclude_dirs) if exclude_dirs else set()
        count = 0

        for dirpath, dirnames, filenames in os.walk(vault_root):
            # Prune excluded directories in-place so os.walk doesn't descend
            dirnames[:] = [d for d in dirnames if d not in exclude]

            for name in filenames:
                if name not in TASKS_FILE_NAMES:
                    continue

                file_path = Path(dirpath) / name
                if self.is_file_stale(file_path):
                    frontmatter, tree = parse_file(file_path)
                    self.update_file(file_path, tree, frontmatter)
                count += 1

        return count

    @abstractmethod
    def clear(self) -> None:
        """Clear the entire cache."""
        pass


class JSONTaskCache(TaskCacheInterface):
    """
    JSON-based task cache implementation.

    In-memory: maps file path (str) to (frontmatter, TaskTree, mtime) tuples.
    On disk: serialized to JSON with recursive task dicts.

    Conversion to/from dicts only happens at the disk boundary (_load/_save).
    """

    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self._files: Dict[str, tuple] = {}  # file_path_str → (frontmatter, TaskTree, mtime|None)
        self._load()

    def _load(self) -> None:
        """Load cache from disk, deserializing dicts into TaskTree objects."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        for file_path_str, entry in data.get('files', {}).items():
            frontmatter = entry.get('frontmatter', [])
            tree = self._dict_to_tree(entry.get('tree', {}), Path(file_path_str))
            mtime = entry.get('mtime')
            self._files[file_path_str] = (frontmatter, tree, mtime)

    def _save(self) -> None:
        """Save cache to disk, serializing TaskTree objects into dicts."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        data = {'files': {}}
        for file_path_str, (frontmatter, tree, mtime) in self._files.items():
            entry = {
                'frontmatter': frontmatter,
                'tree': self._tree_to_dict(tree),
            }
            if mtime is not None:
                entry['mtime'] = mtime
            data['files'][file_path_str] = entry

        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def _task_to_dict(self, task: Task) -> Dict:
        """Convert Task to dict for JSON serialization (recursive)."""
        return {
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'tags': task.tags,
            'notes': task.notes,
            'section': task.section,
            'indent_level': task.indent_level,
            'line_number': task.line_number,
            'children': [self._task_to_dict(child) for child in task.children],
        }

    def _dict_to_task(self, task_dict: Dict) -> Task:
        """Convert dict from JSON into Task object (recursive)."""
        task = Task(
            title=task_dict['title'],
            id=task_dict.get('id'),
            status=task_dict.get('status', 'open'),
            tags=task_dict.get('tags', {}),
            notes=task_dict.get('notes', []),
            section=task_dict.get('section'),
            indent_level=task_dict.get('indent_level', 0),
            line_number=task_dict.get('line_number', 0),
        )
        for child_dict in task_dict.get('children', []):
            task.children.append(self._dict_to_task(child_dict))
        return task

    def _tree_to_dict(self, tree: TaskTree) -> Dict:
        """Convert TaskTree to dict for JSON serialization."""
        return {'tasks': [self._task_to_dict(task) for task in tree.tasks]}

    def _dict_to_tree(self, tree_dict: Dict, file_path: Path) -> TaskTree:
        """Convert dict from JSON into TaskTree object."""
        tasks = [self._dict_to_task(td) for td in tree_dict.get('tasks', [])]
        return TaskTree(tasks=tasks, file_path=file_path)

    def all_trees(self) -> List[TaskTree]:
        return [tree for path, (_, tree, _) in self._files.items()]

    def is_file_stale(self, file_path: Path) -> bool:
        if not file_path.exists():
            return True

        entry = self._files.get(str(file_path))
        if entry is None:
            return True

        _, _, mtime = entry
        return file_path.stat().st_mtime > mtime

    def update_file(self, file_path: Path, tree: TaskTree, frontmatter: Optional[List[str]] = None) -> None:
        tree.file_path = file_path
        mtime = file_path.stat().st_mtime if file_path.exists() else None
        self._files[str(file_path)] = (frontmatter or [], tree, mtime)
        self._save()

    def get_tree(self, file_path: Path) -> Optional[TaskTree]:
        entry = self._files.get(str(file_path))
        if entry is None:
            return None
        _, tree, _ = entry
        return tree

    def get_frontmatter(self, file_path: Path) -> Optional[List[str]]:
        entry = self._files.get(str(file_path))
        if entry is None:
            return None
        frontmatter, _, _ = entry
        return frontmatter

    def find_task(self, task_id: str) -> Optional[Task]:
        for _, (_, tree, _) in self._files.items():
            task = tree.find_by_id(task_id)
            if task:
                return task
        return None

    def find_file(self, task_id: str) -> Optional[Path]:
        for file_path_str, (_, tree, _) in self._files.items():
            if tree.find_by_id(task_id):
                return Path(file_path_str)
        return None

    def get_all_task_ids(self) -> List[str]:
        all_ids = []
        for _, (_, tree, _) in self._files.items():
            for task in tree.all_tasks():
                if task.id:
                    all_ids.append(task.id)
        return all_ids

    def clear(self) -> None:
        self._files = {}
        self._save()


def create_cache(cache_file: Path) -> TaskCacheInterface:
    """
    Factory function to create a cache instance.

    Currently returns JSONTaskCache, but can be extended to return
    different implementations based on configuration.

    Args:
        cache_file: Path to cache file (for JSON) or connection string (for DB)

    Returns:
        TaskCacheInterface implementation
    """
    return JSONTaskCache(cache_file)
