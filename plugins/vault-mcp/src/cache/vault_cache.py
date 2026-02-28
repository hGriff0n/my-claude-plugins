"""
Thread-safe in-memory vault cache with SQLite metadata index.

Design:
    Primary store  — Dict[Path, CachedFile]           (full TaskTree for write-back)
    ID index       — Dict[str, Tuple[Task, Path]]      (O(1) task lookup; Python references)
    SQLite :memory: — tasks table                      (efficient filtered queries)
    Effort store   — Dict[str, Effort]                 (discovered effort dirs)

All mutations acquire _lock (threading.RLock).
The file watcher queues events on _update_queue; a worker thread drains it.
"""

import logging
import queue
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from models.task import CachedFile, SectionBlock, Task, TaskTree
from models.effort import Effort, EffortStatus
from parsers.task_parser import TASK_FILE_NAMES, parse_file, write_file
from parsers.effort_scanner import scan_efforts
from utils.dates import duration_to_minutes
from utils.ids import generate_task_id
from utils.formatting import render_tags

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_CREATE_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    file_path TEXT NOT NULL,
    effort_name TEXT,
    section TEXT,
    indent_level INTEGER NOT NULL DEFAULT 0,
    due_date TEXT,
    scheduled_date TEXT,
    created_date TEXT,
    completed_date TEXT,
    is_stub INTEGER NOT NULL DEFAULT 0,
    has_blockers INTEGER NOT NULL DEFAULT 0,
    estimate_minutes INTEGER,
    parent_id TEXT
);
"""

_CREATE_TASKS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_tasks_status_effort ON tasks (status, effort_name);
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _effort_name_from_path(file_path: Path, vault_root: Path) -> Optional[str]:
    """
    Derive effort name from a task file path.

    Returns the effort directory name if the file lives inside
    $VAULT_ROOT/efforts/<name>/ (active or backlog).
    """
    try:
        rel = file_path.relative_to(vault_root / "efforts")
        parts = rel.parts
        if parts:
            # parts[0] is either the effort name or "__backlog"
            if parts[0] == "__backlog" and len(parts) > 1:
                return parts[1]
            return parts[0]
    except ValueError:
        pass
    return None



def _task_to_row(task: Task, file_path: Path, vault_root: Path, parent_id: Optional[str]) -> dict:
    """Convert a Task to a SQLite row dict."""
    return {
        "id": task.id or "",
        "title": task.title,
        "status": task.status,
        "file_path": str(file_path),
        "effort_name": _effort_name_from_path(file_path, vault_root),
        "section": task.section,
        "indent_level": task.indent_level,
        "due_date": task.tags.get("due"),
        "scheduled_date": task.tags.get("scheduled"),
        "created_date": task.tags.get("created"),
        "completed_date": task.tags.get("completed"),
        "is_stub": 1 if task.is_stub else 0,
        "has_blockers": 1 if task.is_blocked else 0,
        "estimate_minutes": duration_to_minutes(task.tags.get("estimate", "")) or None,
        "parent_id": parent_id,
    }


def _insert_tasks_recursive(
    cursor: sqlite3.Cursor,
    tasks: List[Task],
    file_path: Path,
    vault_root: Path,
    parent_id: Optional[str],
) -> None:
    """Recursively insert tasks and their children into SQLite.

    Every task is expected to have ``task.id`` set before this is called
    (either an explicit user-assigned ID or an auto-generated one from
    ``_upsert_file``).
    """
    for task in tasks:
        row = _task_to_row(task, file_path, vault_root, parent_id)
        cursor.execute(
            """
            INSERT OR REPLACE INTO tasks
            (id, title, status, file_path, effort_name, section, indent_level,
             due_date, scheduled_date, created_date, completed_date,
             is_stub, has_blockers, estimate_minutes, parent_id)
            VALUES
            (:id, :title, :status, :file_path, :effort_name, :section, :indent_level,
             :due_date, :scheduled_date, :created_date, :completed_date,
             :is_stub, :has_blockers, :estimate_minutes, :parent_id)
            """,
            row,
        )
        _insert_tasks_recursive(cursor, task.children, file_path, vault_root, task.id)


# ---------------------------------------------------------------------------
# VaultCache
# ---------------------------------------------------------------------------

class VaultCache:
    """
    Thread-safe in-memory vault cache.

    Initialize with initialize(), then start the background worker with
    start_worker(). The watcher calls enqueue_refresh() to schedule file
    re-parses without blocking the watcher thread.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._files: Dict[Path, CachedFile] = {}
        self._tasks_by_id: Dict[str, Tuple[Task, Path]] = {}
        self._efforts: Dict[str, Effort] = {}
        self._vault_root: Optional[Path] = None
        self._exclude_dirs: Set[str] = set()
        self._db: sqlite3.Connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_CREATE_TASKS_TABLE + _CREATE_TASKS_INDEX)
        self._update_queue: "queue.Queue[Optional[Path]]" = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_full_scan: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self, vault_root: Path, exclude_dirs: Set[str]) -> None:
        """
        Full vault scan. Blocks until complete.
        Call once at server startup before starting the watcher.
        """
        self._vault_root = vault_root
        self._exclude_dirs = exclude_dirs
        log.info("Starting vault scan: %s", vault_root)
        self._full_scan()
        self._last_full_scan = datetime.now()
        log.info(
            "Vault scan complete: %d files, %d tasks, %d efforts",
            len(self._files),
            len(self._tasks_by_id),
            len(self._efforts),
        )

    def start_worker(self) -> None:
        """Start the background queue-drain worker thread (daemon)."""
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="vault-cache-worker"
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        """Signal the worker thread to stop and wait for it."""
        self._update_queue.put(None)  # sentinel
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Internal scanning
    # ------------------------------------------------------------------

    def _full_scan(self) -> None:
        """Walk the vault and parse all task files + efforts."""
        assert self._vault_root is not None

        # Scan task files
        for path in self._walk_task_files(self._vault_root):
            self._load_file(path)

        # Scan efforts
        efforts_root = self._vault_root / "efforts"
        discovered = scan_efforts(efforts_root)
        with self._lock:
            self._efforts = discovered

    def _walk_task_files(self, root: Path) -> Iterator[Path]:
        """Yield all TASKS.md / 01 TASKS.md paths under root, respecting exclusions."""
        for path in root.rglob("*"):
            if path.name in TASK_FILE_NAMES:
                # Check if any parent component is excluded
                try:
                    rel = path.relative_to(root)
                    if any(part in self._exclude_dirs for part in rel.parts[:-1]):
                        continue
                except ValueError:
                    continue
                yield path

    def _load_file(self, path: Path) -> None:
        """Parse a task file and add it to the cache (no lock — internal use)."""
        try:
            mtime = path.stat().st_mtime
            tree = parse_file(path)
            cached = CachedFile(file_path=path, tree=tree, mtime=mtime)
            self._upsert_file(cached)
        except Exception:
            log.exception("Failed to parse %s", path)

    def _upsert_file(self, cached: CachedFile) -> None:
        """
        Store a CachedFile in all indexes. Caller must hold _lock or call
        from single-threaded init.
        """
        path = cached.file_path

        # Remove old entries for this file from SQLite and id index
        old = self._files.get(path)
        if old:
            old_ids = [t.id for t in old.tree.all_tasks() if t.id]
            for tid in old_ids:
                self._tasks_by_id.pop(tid, None)
            self._db.execute("DELETE FROM tasks WHERE file_path = ?", (str(path),))

        # Assign real IDs to tasks that lack explicit ones.
        # This happens BEFORE indexing so every task has an ID for SQLite
        # and _tasks_by_id.  The ID is also added to task.tags["id"] so
        # that write_file will persist it to disk.
        all_tasks = cached.tree.all_tasks()
        existing_ids = set(self._tasks_by_id.keys())
        needs_write = False
        for task in all_tasks:
            if task.id:
                existing_ids.add(task.id)
        for task in all_tasks:
            if not task.id:
                new_id = generate_task_id()
                while new_id in existing_ids:
                    new_id = generate_task_id()
                task.id = new_id
                task.tags["id"] = new_id
                existing_ids.add(new_id)
                needs_write = True

        # Write back to disk if we assigned any new IDs
        if needs_write:
            write_file(path, cached.tree)
            cached.mtime = path.stat().st_mtime

        # Store new
        self._files[path] = cached

        for task in all_tasks:
            self._tasks_by_id[task.id] = (task, path)

        # Insert into SQLite (all root sections)
        cursor = self._db.cursor()
        for section in cached.tree.sections:
            _insert_tasks_recursive(cursor, section.tasks, path, self._vault_root, None)
        self._db.commit()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Drain the update queue, re-parsing files as they arrive."""
        while True:
            item = self._update_queue.get()
            if item is None:  # sentinel → stop
                break
            try:
                self.refresh_file(item)
            except Exception:
                log.exception("Worker failed to refresh %s", item)

    # ------------------------------------------------------------------
    # Public cache refresh methods
    # ------------------------------------------------------------------

    def enqueue_refresh(self, path: Path) -> None:
        """
        Schedule a file re-parse from a watcher callback (non-blocking).
        """
        self._update_queue.put(path)

    def enqueue_effort_scan(self) -> None:
        """Schedule a full effort re-scan."""
        self._update_queue.put(self._vault_root / "efforts")  # special sentinel path

    def refresh_file(self, path: Path) -> None:
        """
        Re-parse a single task file and update all indexes.
        Thread-safe; blocks on _lock.
        """
        # Special case: effort scan was enqueued
        if self._vault_root and path == self._vault_root / "efforts":
            self.refresh_efforts()
            return

        if path.name not in TASK_FILE_NAMES:
            return

        if not path.exists():
            self._remove_file(path)
            return

        try:
            mtime = path.stat().st_mtime
        except OSError:
            return

        with self._lock:
            existing = self._files.get(path)
            if existing and existing.mtime >= mtime:
                return  # Already up to date
            self._load_file(path)

    def _remove_file(self, path: Path) -> None:
        """Remove a deleted file from all indexes."""
        with self._lock:
            cached = self._files.pop(path, None)
            if not cached:
                return
            for task in cached.tree.all_tasks():
                if task.id:
                    self._tasks_by_id.pop(task.id, None)
            self._db.execute("DELETE FROM tasks WHERE file_path = ?", (str(path),))
            self._db.commit()

    def refresh_efforts(self) -> None:
        """Re-scan the efforts directory and update the effort map."""
        if not self._vault_root:
            return
        discovered = scan_efforts(self._vault_root / "efforts")
        with self._lock:
            self._efforts = discovered

    # ------------------------------------------------------------------
    # Task queries
    # ------------------------------------------------------------------

    def query_tasks(
        self,
        *,
        status: Optional[str] = None,
        effort: Optional[str] = None,
        due_before: Optional[str] = None,
        scheduled_before: Optional[str] = None,
        scheduled_on: Optional[str] = None,
        stub: Optional[bool] = None,
        blocked: Optional[bool] = None,
        file_path: Optional[Path] = None,
        parent_id: Optional[str] = None,
        include_subtasks: bool = False,
        limit: int = 500,
    ) -> List[Task]:
        """
        Query tasks using the SQLite index; resolve full Task objects from memory.

        Args:
            status: Comma-separated statuses e.g. "open,in-progress"
            effort: Effort name
            due_before: ISO date string — return tasks due on or before this date
            scheduled_before: ISO date string — return tasks scheduled on or before this date
            scheduled_on: ISO date string — return tasks scheduled on exactly this date
            stub: If True, only stubs; False, exclude stubs
            blocked: If True, only blocked; False, exclude blocked
            file_path: Restrict to a specific file
            parent_id: Only return direct children of this task ID
            include_subtasks: If True, also return sub-tasks of every matched
                task (even if the sub-tasks themselves don't match the filters).
                Defaults to False.
            limit: Max results

        Returns:
            List of Task objects (Python references from in-memory store)
        """
        clauses = []
        params: list = []

        if status:
            statuses = [s.strip() for s in status.split(",")]
            placeholders = ",".join("?" * len(statuses))
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)

        if effort:
            clauses.append("effort_name = ?")
            params.append(effort)

        if due_before:
            clauses.append("due_date IS NOT NULL AND due_date <= ?")
            params.append(due_before)

        if scheduled_before:
            clauses.append("scheduled_date IS NOT NULL AND scheduled_date <= ?")
            params.append(scheduled_before)

        if scheduled_on:
            clauses.append("scheduled_date = ?")
            params.append(scheduled_on)

        if stub is not None:
            clauses.append("is_stub = ?")
            params.append(1 if stub else 0)

        if blocked is not None:
            clauses.append("has_blockers = ?")
            params.append(1 if blocked else 0)

        if file_path:
            clauses.append("file_path = ?")
            params.append(str(file_path))

        if parent_id:
            clauses.append("parent_id = ?")
            params.append(parent_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT id FROM tasks {where} LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
            tasks = []
            seen_ids: Set[str] = set()
            for row in rows:
                entry = self._tasks_by_id.get(row["id"])
                if entry:
                    tasks.append(entry[0])
                    seen_ids.add(row["id"])

            # Optionally expand: for each matched task, also pull in its
            # sub-tasks (recursively) even if they didn't match the filters.
            if include_subtasks:
                extra: List[Task] = []
                for task in list(tasks):
                    for child in task.all_tasks()[1:]:  # skip self
                        if child.id and child.id not in seen_ids:
                            extra.append(child)
                            seen_ids.add(child.id)
                tasks.extend(extra)

            return tasks

    def get_task(self, task_id: str) -> Optional[Tuple[Task, Path]]:
        """Return (Task, file_path) or None."""
        with self._lock:
            return self._tasks_by_id.get(task_id)

    def get_task_file(self, task_id: str) -> Optional[Path]:
        """Return the file path containing this task, or None."""
        entry = self.get_task(task_id)
        return entry[1] if entry else None

    def get_all_task_ids(self) -> List[str]:
        """Return all known task IDs."""
        with self._lock:
            return list(self._tasks_by_id.keys())

    # ------------------------------------------------------------------
    # Task mutations (write-through to disk)
    # ------------------------------------------------------------------

    def add_task(
        self,
        file_path: Path,
        title: str,
        *,
        section: Optional[str] = None,
        status: str = "open",
        tags: Optional[Dict] = None,
        parent_id: Optional[str] = None,
    ) -> Task:
        """
        Add a new task to a file. Auto-generates a unique ID.

        New tasks are marked #stub by default (indicating they need subtasks).
        To suppress this, include ``{"stub": None}`` in tags and pop it after
        calling, or simply remove the stub tag from the returned task if not needed.

        Args:
            file_path: Target TASKS.md file
            title: Task title
            section: Section heading to add under (creates if missing)
            status: Initial status
            tags: Additional tags dict
            parent_id: ID of parent task (makes this a subtask)

        Returns:
            The new Task object (re-parsed from disk with correct line numbers)
        """
        from utils.ids import generate_task_id
        from datetime import date

        with self._lock:
            # Generate a unique ID
            existing_ids = set(self._tasks_by_id.keys())
            new_id = generate_task_id()
            while new_id in existing_ids:
                new_id = generate_task_id()

            all_tags = dict(tags or {})
            all_tags["id"] = new_id
            all_tags["created"] = date.today().isoformat()
            all_tags.setdefault("stub", "")

            new_task = Task(
                title=title,
                id=new_id,
                status=status,
                tags=all_tags,
            )

            cached = self._files.get(file_path)
            if cached is None:
                # File doesn't exist yet or not in cache — create empty tree
                tree = TaskTree(file_path=file_path)
                cached = CachedFile(file_path=file_path, tree=tree, mtime=0.0)
                self._files[file_path] = cached

            tree = cached.tree

            if parent_id:
                parent_task = tree.find_by_id(parent_id)
                if parent_task:
                    new_task.indent_level = parent_task.indent_level + 1
                    new_task.section = parent_task.section
                    new_task.section_level = parent_task.section_level
                    parent_task.children.append(new_task)
                    # Remove #stub from parent if it had one
                    parent_task.tags.pop("stub", None)
            else:
                target_section = None
                if section:
                    target_section = tree.find_section(section)
                    if not target_section:
                        target_section = SectionBlock(heading=section, level=3)
                        tree.sections.append(target_section)
                elif tree.sections:
                    target_section = tree.sections[0]
                else:
                    target_section = SectionBlock(heading="Open", level=3)
                    tree.sections.append(target_section)

                new_task.section = target_section.heading
                new_task.section_level = target_section.level
                target_section.tasks.append(new_task)

            write_file(file_path, tree)
            self._load_file(file_path)

            # Return the re-parsed task so file_path and line_number are correct
            refreshed = self._tasks_by_id.get(new_id)
            return refreshed[0] if refreshed else new_task

    def update_task(self, task_id: str, **changes) -> Optional[Task]:
        """
        Update task fields and write back to disk.

        Supported changes: title, status, due, scheduled, estimate,
                           blocked_by (list[str]), unblock (list[str])

        Returns the updated Task or None if not found.
        """
        from datetime import date

        with self._lock:
            entry = self._tasks_by_id.get(task_id)
            if not entry:
                return None
            task, file_path = entry

            if "title" in changes:
                task.title = changes["title"]

            if "status" in changes:
                new_status = changes["status"]
                task.status = new_status
                if new_status == "done" and "completed" not in task.tags:
                    task.tags["completed"] = date.today().isoformat()
                elif new_status != "done":
                    task.tags.pop("completed", None)

            for tag_key in ("due", "scheduled", "estimate"):
                if tag_key in changes:
                    val = changes[tag_key]
                    if val:
                        task.tags[tag_key] = val
                    else:
                        task.tags.pop(tag_key, None)

            if "blocked_by" in changes:
                for bid in changes["blocked_by"]:
                    task.add_blocker(bid)

            if "unblock" in changes:
                for bid in changes["unblock"]:
                    task.remove_blocker(bid)

            cached = self._files[file_path]
            write_file(file_path, cached.tree)
            self._load_file(file_path)

            return self._tasks_by_id.get(task_id, (None, None))[0]

    # ------------------------------------------------------------------
    # Effort queries + mutations
    # ------------------------------------------------------------------

    def get_effort(self, name: str) -> Optional[Effort]:
        with self._lock:
            return self._efforts.get(name)

    def list_efforts(self, status: Optional[str] = None) -> List[Effort]:
        with self._lock:
            efforts = list(self._efforts.values())
            if status:
                efforts = [e for e in efforts if e.status.value == status]
            return sorted(efforts, key=lambda e: e.name)

    @property
    def vault_root(self) -> Optional[Path]:
        return self._vault_root

    def set_effort_status(self, name: str, status: EffortStatus) -> None:
        """
        Update the status of an effort in the cache.
        Note: This does NOT move files on disk — effort status is determined
        by directory structure (__backlog/) which the user manages manually.
        """
        with self._lock:
            effort = self._efforts.get(name)
            if not effort:
                raise ValueError(f"Effort '{name}' not found")
            effort.status = status

    # ------------------------------------------------------------------
    # Status / diagnostics
    # ------------------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            return {
                "files_indexed": len(self._files),
                "tasks_indexed": len(self._tasks_by_id),
                "efforts_indexed": len(self._efforts),
                "last_full_scan": self._last_full_scan.isoformat() if self._last_full_scan else None,
                "vault_root": str(self._vault_root) if self._vault_root else None,
                "exclude_dirs": sorted(self._exclude_dirs),
            }

    def is_file_stale(self, path: Path) -> bool:
        """Return True if file has been modified since last parse."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            cached = self._files.get(path)
            return cached is None or cached.mtime < mtime


