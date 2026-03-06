"""
Vault file system watcher — polling-based.

Docker volume mounts from Windows do not forward filesystem events (inotify)
into the container, so we use periodic mtime polling instead of watchdog's
event-based Observer.

The watcher runs a daemon thread that:
1. Walks VAULT_ROOT every POLL_INTERVAL seconds
2. Compares file mtimes against the cache's stored mtimes
3. Enqueues refresh for any files that changed, appeared, or disappeared
4. Re-scans efforts/ when any change is detected under that directory
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

from parsers.task_parser import TASK_FILE_NAMES

log = logging.getLogger(__name__)

# Default polling interval in seconds (configurable via POLL_INTERVAL env var)
_DEFAULT_POLL_INTERVAL = 5.0


class VaultWatcher:
    """
    Polling-based vault watcher.

    Periodically walks the vault directory, detects new/modified/deleted task
    files by comparing mtimes, and enqueues cache refreshes.

    Usage:
        watcher = VaultWatcher(cache, vault_root, exclude_dirs)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(
        self,
        cache,
        vault_root: Path,
        exclude_dirs: Set[str],
        poll_interval: Optional[float] = None,
    ) -> None:
        self._cache = cache
        self._vault_root = vault_root
        self._exclude_dirs = exclude_dirs
        self._poll_interval = poll_interval or float(
            os.environ.get("POLL_INTERVAL", _DEFAULT_POLL_INTERVAL)
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Track known files and their mtimes from the last poll cycle
        self._known_files: Dict[Path, float] = {}
        # Track effort dir mtimes (any CLAUDE.md under efforts/)
        self._efforts_mtime: float = 0.0

    def start(self) -> None:
        """Start the polling thread (daemon)."""
        log.info(
            "Starting vault watcher (polling every %.1fs)", self._poll_interval
        )
        # Seed known files from the current state
        self._known_files = self._snapshot_task_files()
        self._efforts_mtime = self._snapshot_efforts_mtime()

        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="vault-watcher"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the poll thread to stop and wait for it."""
        log.info("Stopping vault watcher")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._poll_interval + 2)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Main polling loop — runs until stop_event is set."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._poll_interval)
            if self._stop_event.is_set():
                break
            try:
                self._check_for_changes()
            except Exception:
                log.exception("Error during poll cycle")

    def _check_for_changes(self) -> None:
        """Single poll cycle: compare current state vs known state."""
        current_files = self._snapshot_task_files()

        # Detect new or modified files
        for path, mtime in current_files.items():
            old_mtime = self._known_files.get(path)
            if old_mtime is None:
                log.debug("New task file detected: %s", path)
                self._cache.enqueue_refresh(path)
            elif mtime > old_mtime:
                log.debug("Modified task file: %s", path)
                self._cache.enqueue_refresh(path)

        # Detect deleted files
        for path in self._known_files:
            if path not in current_files:
                log.debug("Deleted task file: %s", path)
                self._cache.enqueue_refresh(path)

        self._known_files = current_files

        # Check if efforts directory changed
        current_efforts_mtime = self._snapshot_efforts_mtime()
        if current_efforts_mtime != self._efforts_mtime:
            log.debug("Efforts directory changed, scheduling re-scan")
            self._cache.enqueue_effort_scan()
            self._efforts_mtime = current_efforts_mtime

    def _snapshot_task_files(self) -> Dict[Path, float]:
        """Walk the vault and return {path: mtime} for all task files."""
        snapshot: Dict[Path, float] = {}
        try:
            for path in self._vault_root.rglob("*"):
                if path.name not in TASK_FILE_NAMES:
                    continue
                # Check exclusions
                try:
                    rel = path.relative_to(self._vault_root)
                    if any(part in self._exclude_dirs for part in rel.parts[:-1]):
                        continue
                except ValueError:
                    continue
                try:
                    snapshot[path] = path.stat().st_mtime
                except OSError:
                    pass
        except OSError:
            log.exception("Error walking vault for task files")
        return snapshot

    def _snapshot_efforts_mtime(self) -> float:
        """
        Return a composite mtime for the efforts/ directory tree.

        We hash together the mtimes of all CLAUDE.md files and directory
        entries under efforts/ to detect any structural change (new effort,
        deleted effort, moved effort).
        """
        efforts_root = self._vault_root / "efforts"
        if not efforts_root.is_dir():
            return 0.0

        max_mtime = 0.0
        try:
            for path in efforts_root.rglob("*"):
                if path.name == "CLAUDE.md" or path.is_dir():
                    try:
                        mt = path.stat().st_mtime
                        if mt > max_mtime:
                            max_mtime = mt
                    except OSError:
                        pass
        except OSError:
            pass
        return max_mtime
