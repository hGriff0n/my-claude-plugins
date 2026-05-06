"""
Vault watcher.

Implements the inbound half of `specs/components/asyncfile.md`:

- Watch criteria are `(target, events)` where target is always a specific
  file or folder (no prefix matching).
- `register(criterion, callback)` returns a `WatcherHandle` and synchronously
  invokes the callback for every existing matching path before returning,
  with the new handle as active origin. Recursively re-enters for any
  watchers the callback registers.
- A polling loop drives live events (Docker bind mounts on Windows do not
  forward inotify events, so polling is the portable choice).
- Events are coalesced per (handle, file) for a short window to absorb
  editor save-storms.
- A self-write registry suppresses events whose paths the debouncer (or
  parser write backends) just touched.
- The currently firing handle is exposed as the *active origin* via a
  `ContextVar`; callers performing DB writes inside a callback pass it
  through to the database so the debouncer can suppress backport.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

log = logging.getLogger(__name__)


class EventType(Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


@dataclass(frozen=True)
class WatchCriterion:
    target: Path
    events: FrozenSet[EventType]


Callback = Callable[[Path, EventType, "WatcherHandle"], None]


@dataclass
class WatcherHandle:
    id: int
    target: Path
    events: FrozenSet[EventType]
    callback: Callback

    def __hash__(self) -> int:
        return self.id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WatcherHandle) and other.id == self.id


_active_origin: contextvars.ContextVar[Optional[WatcherHandle]] = (
    contextvars.ContextVar("active_origin", default=None)
)


def active_origin() -> Optional[WatcherHandle]:
    """The handle currently dispatching, or None outside a callback."""
    return _active_origin.get()


@dataclass
class _WatchState:
    """Last-observed state for a watched target, used to detect events."""

    exists: bool = False
    mtime: float = 0.0
    # For folder targets: snapshot of immediate child names
    children: Set[str] = field(default_factory=set)


@dataclass
class _PendingEvent:
    last_seen: float
    event: EventType


class Watcher:
    """Polling-based file watcher with immediate-fire-on-register semantics."""

    def __init__(
        self,
        poll_interval: float = 1.0,
        coalesce_window: float = 0.2,
        self_write_window: float = 2.0,
    ) -> None:
        self._poll_interval = poll_interval
        self._coalesce_window = coalesce_window
        self._self_write_window = self_write_window

        self._lock = threading.RLock()
        self._handles: Dict[int, WatcherHandle] = {}
        self._state: Dict[int, _WatchState] = {}
        self._pending: Dict[Tuple[int, Path], _PendingEvent] = {}
        self._self_writes: Dict[Path, float] = {}
        self._next_id = 1

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Surface
    # ------------------------------------------------------------------

    def register(
        self,
        criterion: WatchCriterion,
        callback: Callback,
    ) -> WatcherHandle:
        """Register a watcher and immediately fire CREATE for current state.

        Idempotent on identical (criterion, callback). The synchronous
        immediate-fire pass runs with the new handle as active origin so DB
        writes inside the callback are correctly attributed.
        """
        with self._lock:
            for existing in self._handles.values():
                if (
                    existing.target == criterion.target
                    and existing.events == criterion.events
                    and existing.callback is callback
                ):
                    return existing

            handle = WatcherHandle(
                id=self._next_id,
                target=criterion.target,
                events=criterion.events,
                callback=callback,
            )
            self._next_id += 1
            self._handles[handle.id] = handle
            self._state[handle.id] = _WatchState()

        # Immediate fire is synchronous and outside the lock so that any
        # nested register() calls from the callback can take it.
        self._fire_initial(handle)
        return handle

    def deregister(self, handle: WatcherHandle) -> None:
        with self._lock:
            self._handles.pop(handle.id, None)
            self._state.pop(handle.id, None)
            for key in list(self._pending):
                if key[0] == handle.id:
                    del self._pending[key]

    def retarget(self, handle: WatcherHandle, new_target: Path) -> None:
        """Move a watcher's target without changing handle identity."""
        with self._lock:
            stored = self._handles.get(handle.id)
            if stored is None:
                return
            stored.target = new_target
            handle.target = new_target
            self._state[handle.id] = _WatchState()

    def mark_self_write(self, path: Path) -> None:
        """Suppress the next file event for `path` (within the window)."""
        with self._lock:
            self._self_writes[path] = time.monotonic() + self._self_write_window

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, name="vault-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 2)
            self._thread = None

    # ------------------------------------------------------------------
    # Immediate fire
    # ------------------------------------------------------------------

    def _fire_initial(self, handle: WatcherHandle) -> None:
        """Synchronously fire CREATE for current matching state.

        Per spec, this fires regardless of whether CREATE is in the
        criterion's events — it is the seed mechanism, not a regular event.
        """
        target = handle.target
        if target.exists():
            self._snapshot(handle)
            self._dispatch(handle, target, EventType.CREATE)

    def _snapshot(self, handle: WatcherHandle) -> None:
        """Record the current on-disk state for change detection."""
        target = handle.target
        state = self._state[handle.id]
        if target.exists():
            state.exists = True
            try:
                state.mtime = target.stat().st_mtime
            except OSError:
                state.mtime = 0.0
            if target.is_dir():
                try:
                    state.children = {p.name for p in target.iterdir()}
                except OSError:
                    state.children = set()
        else:
            state.exists = False
            state.mtime = 0.0
            state.children = set()

    def _dispatch(
        self, handle: WatcherHandle, file: Path, event: EventType
    ) -> None:
        """Invoke a callback with the handle as active origin."""
        token = _active_origin.set(handle)
        try:
            handle.callback(file, event, handle)
        except Exception:
            log.exception(
                "Watcher callback failed (handle=%d, target=%s, event=%s)",
                handle.id, handle.target, event.value,
            )
        finally:
            _active_origin.reset(token)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._poll_interval)
            if self._stop.is_set():
                break
            try:
                self._scan_once()
                self._flush_pending()
            except Exception:
                log.exception("Watcher poll cycle failed")

    def _scan_once(self) -> None:
        """Detect raw events for every registered handle."""
        with self._lock:
            handles = list(self._handles.values())

        for handle in handles:
            try:
                self._scan_handle(handle)
            except Exception:
                log.exception("Watcher scan failed (handle=%d)", handle.id)

    def _scan_handle(self, handle: WatcherHandle) -> None:
        target = handle.target
        with self._lock:
            state = self._state.get(handle.id)
            if state is None:
                return

        existed = state.exists
        exists = target.exists()

        if existed and not exists:
            self._maybe_enqueue(handle, target, EventType.DELETE)
            with self._lock:
                state.exists = False
                state.mtime = 0.0
                state.children = set()
            return

        if not existed and exists:
            self._maybe_enqueue(handle, target, EventType.CREATE)
            with self._lock:
                self._snapshot(handle)
            return

        if not exists:
            return

        # Existed before and still exists — check for modify.
        try:
            mtime = target.stat().st_mtime
        except OSError:
            return

        modified = mtime > state.mtime
        if target.is_dir():
            try:
                children = {p.name for p in target.iterdir()}
            except OSError:
                children = state.children
            if children != state.children:
                modified = True
                with self._lock:
                    state.children = children

        if modified:
            self._maybe_enqueue(handle, target, EventType.MODIFY)
            with self._lock:
                state.mtime = mtime

    def _maybe_enqueue(
        self, handle: WatcherHandle, file: Path, event: EventType
    ) -> None:
        if event not in handle.events:
            return
        if self._consume_self_write(file):
            return
        with self._lock:
            self._pending[(handle.id, file)] = _PendingEvent(
                last_seen=time.monotonic(), event=event
            )

    def _consume_self_write(self, path: Path) -> bool:
        """Consume a self-write entry for `path` if present and unexpired."""
        with self._lock:
            expiry = self._self_writes.get(path)
            now = time.monotonic()
            if expiry is None:
                # Drop expired entries opportunistically.
                stale = [p for p, e in self._self_writes.items() if e < now]
                for p in stale:
                    del self._self_writes[p]
                return False
            if expiry < now:
                del self._self_writes[path]
                return False
            del self._self_writes[path]
            return True

    def _flush_pending(self) -> None:
        """Fire callbacks for buckets that have gone quiet.

        Dispatch is ordered by descending target depth so that watchers
        on deeper paths (e.g. per-task-file) complete before watchers on
        shallower paths (per-effort folder, root). This lets task-level
        callbacks settle the DB before the parent effort's event fires.
        """
        now = time.monotonic()
        ready: List[Tuple[WatcherHandle, Path, EventType]] = []
        with self._lock:
            for key, pending in list(self._pending.items()):
                if now - pending.last_seen >= self._coalesce_window:
                    handle = self._handles.get(key[0])
                    if handle is not None:
                        ready.append((handle, key[1], pending.event))
                    del self._pending[key]

        ready.sort(key=lambda r: len(r[0].target.parts), reverse=True)
        for handle, file, event in ready:
            self._dispatch(handle, file, event)
