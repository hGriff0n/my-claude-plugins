"""
Write debouncer.

Implements the outbound half of `specs/components/asyncfile.md`: pending
DB-first edits are coalesced per parent file and projected back to disk
after the owning system's lag.

A small write-ahead log persists pending mutations so that updates which
have not yet been backported survive a process crash. On startup the
log is replayed against the database (with origin=None so the debouncer
re-enqueues the backport).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel

log = logging.getLogger(__name__)


ParentFileResolver = Callable[[BaseModel], Optional[Path]]
Writer = Callable[[Path, List[BaseModel]], None]
ElementsForFile = Callable[[Path], List[BaseModel]]


def _identity_value(elem: BaseModel) -> Any:
    fields = type(elem).model_fields
    if "id" in fields:
        return getattr(elem, "id")
    if "name" in fields:
        return getattr(elem, "name")
    return None


def _table_name_for(model: Type[BaseModel]) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()


def _db_lookup(db: Any, elem: BaseModel) -> Optional[BaseModel]:
    fields = type(elem).model_fields
    field = "id" if "id" in fields else "name" if "name" in fields else None
    if field is None:
        return None
    value = getattr(elem, field, None)
    if value is None:
        return None
    table = _table_name_for(type(elem))
    try:
        rows = db.query(f'SELECT * FROM "{table}"')
    except Exception:
        return None
    for row in rows:
        if getattr(row, field, None) == value:
            return row
    return None


def _db_matches(db: Any, elem: BaseModel, payload: Any) -> bool:
    existing = _db_lookup(db, elem)
    if existing is None:
        return False
    return existing.model_dump(mode="json") == payload


@dataclass
class _SystemConfig:
    name: str
    lag: timedelta
    parent_file_resolver: ParentFileResolver
    writer: Writer
    elements_for_file: ElementsForFile
    models: Dict[str, Type[BaseModel]] = field(default_factory=dict)


@dataclass
class _PendingEntry:
    file: Path
    system: str
    eligible_at: float


class WriteDebouncer:
    """Coalesces DB→file backports and persists pending updates to a WAL."""

    def __init__(
        self,
        watcher: Any,
        wal_path: Path,
        resolver_interval: float = 0.5,
    ) -> None:
        self._watcher = watcher
        self._wal_path = wal_path
        self._resolver_interval = resolver_interval

        self._lock = threading.RLock()
        self._systems: Dict[str, _SystemConfig] = {}
        self._pending: Dict[Path, _PendingEntry] = {}

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._wal_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # System registration
    # ------------------------------------------------------------------

    def register_system(
        self,
        name: str,
        lag: timedelta,
        parent_file_resolver: ParentFileResolver,
        writer: Writer,
        elements_for_file: ElementsForFile,
        models: Optional[Dict[str, Type[BaseModel]]] = None,
    ) -> None:
        """Configure a system's lag, resolver, writer, and WAL model map.

        `elements_for_file(path)` returns the current authoritative list of
        elements (from the database) that belong to `path` — used by the
        debouncer to project the file. `models` maps the registered model
        class names to their types so the WAL can deserialize entries.
        """
        with self._lock:
            self._systems[name] = _SystemConfig(
                name=name,
                lag=lag,
                parent_file_resolver=parent_file_resolver,
                writer=writer,
                elements_for_file=elements_for_file,
                models=dict(models or {}),
            )

    # ------------------------------------------------------------------
    # Surface
    # ------------------------------------------------------------------

    def enqueue(self, file: Path, system: str) -> None:
        """Schedule `file` for re-projection after the system's lag.

        Systems with lag=0 are write-through: the projection happens
        synchronously on the calling thread (no resolver tick needed).
        """
        with self._lock:
            cfg = self._systems.get(system)
            if cfg is None:
                log.warning("enqueue: unknown system %r", system)
                return
            if cfg.lag.total_seconds() <= 0:
                self._pending.pop(file, None)
                entry = _PendingEntry(
                    file=file, system=system, eligible_at=time.monotonic(),
                )
                # Write-through: surface failures to the caller.
                self._project(entry, swallow=False)
                return
            eligible_at = time.monotonic() + cfg.lag.total_seconds()
            existing = self._pending.get(file)
            if existing is None or eligible_at > existing.eligible_at:
                self._pending[file] = _PendingEntry(
                    file=file, system=system, eligible_at=eligible_at,
                )

    def flush(self, file: Optional[Path] = None) -> None:
        """Force immediate backport for `file` (or every pending entry)."""
        with self._lock:
            if file is None:
                entries = list(self._pending.values())
                self._pending.clear()
            else:
                entry = self._pending.pop(file, None)
                entries = [entry] if entry is not None else []

        for entry in entries:
            self._project(entry)

    def system_for_model(self, model: Type[BaseModel]) -> Optional[str]:
        """Find which registered system owns `model`."""
        with self._lock:
            for cfg in self._systems.values():
                if model in cfg.models.values():
                    return cfg.name
        return None

    def parent_file(self, system: str, elem: BaseModel) -> Optional[Path]:
        with self._lock:
            cfg = self._systems.get(system)
        if cfg is None:
            return None
        return cfg.parent_file_resolver(elem)

    def lag(self, system: str) -> timedelta:
        with self._lock:
            cfg = self._systems.get(system)
        return cfg.lag if cfg is not None else timedelta(0)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="write-debouncer", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._resolver_interval + 2)
            self._thread = None
        self.flush()

    # ------------------------------------------------------------------
    # Resolver loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._resolver_interval)
            if self._stop.is_set():
                break
            try:
                self._tick()
            except Exception:
                log.exception("Debouncer tick failed")

    def _tick(self) -> None:
        now = time.monotonic()
        ready: List[_PendingEntry] = []
        with self._lock:
            for file, entry in list(self._pending.items()):
                if entry.eligible_at <= now:
                    ready.append(entry)
                    del self._pending[file]

        for entry in ready:
            self._project(entry)

    def _project(self, entry: _PendingEntry, swallow: bool = True) -> None:
        cfg = self._systems.get(entry.system)
        if cfg is None:
            log.warning("Skip projection: unknown system %r", entry.system)
            return
        try:
            elements = cfg.elements_for_file(entry.file)
            self._watcher.mark_self_write(entry.file)
            cfg.writer(entry.file, elements)
        except Exception:
            log.exception(
                "Backport failed for %s (system=%s)", entry.file, entry.system,
            )
            if swallow:
                return
            raise
        self._wal_clear_for_file(entry.file)

    # ------------------------------------------------------------------
    # Write-ahead log
    # ------------------------------------------------------------------

    def wal_record(
        self,
        system: str,
        elem: BaseModel,
        deleted: bool,
        file: Path,
    ) -> None:
        """Record a pending mutation, replacing any prior entry for this element.

        Keyed by `(system, model, identity)` so a second update to the same
        element collapses the earlier entry — latest write wins.
        """
        identity = _identity_value(elem)
        model_name = type(elem).__name__
        record = {
            "system": system,
            "model": model_name,
            "identity": identity,
            "deleted": deleted,
            "file": str(file),
            "payload": elem.model_dump(mode="json"),
        }
        new_line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            kept = self._wal_read_filtered(
                exclude_key=(system, model_name, identity),
            )
            kept.append(new_line)
            self._wal_write(kept)

    def _wal_read_filtered(
        self,
        *,
        exclude_key: Optional[Tuple[str, str, Any]] = None,
        exclude_file: Optional[str] = None,
    ) -> List[str]:
        """Read WAL lines, dropping ones matching the given filters."""
        if not self._wal_path.exists():
            return []
        kept: List[str] = []
        with self._wal_path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if exclude_file is not None and rec.get("file") == exclude_file:
                    continue
                if exclude_key is not None:
                    key = (
                        rec.get("system"),
                        rec.get("model"),
                        rec.get("identity"),
                    )
                    if key == exclude_key:
                        continue
                kept.append(line)
        return kept

    def _wal_write(self, lines: List[str]) -> None:
        tmp = self._wal_path.with_suffix(self._wal_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        tmp.replace(self._wal_path)

    def pending_elements(self, file: Path) -> List[BaseModel]:
        """Return deserialized pending elements for `file`.

        Used by parsers during inbound reconciliation: when the watcher
        re-parses a file with outstanding pending writes, the parser can
        match unidentified parsed elements against these candidates rather
        than creating duplicates. Deletions are excluded.
        """
        with self._lock:
            if not self._wal_path.exists():
                return []
            target = str(file)
            result: List[BaseModel] = []
            with self._wal_path.open("r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.rstrip("\n")
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("file") != target or rec.get("deleted"):
                        continue
                    cfg = self._systems.get(rec.get("system"))
                    if cfg is None:
                        continue
                    model_cls = cfg.models.get(rec.get("model"))
                    if model_cls is None:
                        continue
                    try:
                        result.append(model_cls.model_validate(rec["payload"]))
                    except Exception:
                        log.exception("pending_elements: payload validation failed")
            return result

    def _wal_clear_for_file(self, file: Path) -> None:
        with self._lock:
            if not self._wal_path.exists():
                return
            kept = self._wal_read_filtered(exclude_file=str(file))
            self._wal_write(kept)

    def wal_replay(self, db: Any) -> int:
        """Re-apply WAL entries to the database with origin=None.

        For each entry, compare against current DB state: if the DB already
        matches the WAL payload, skip (the mutation reached the DB before
        the crash). Otherwise re-apply, which re-enters the normal write
        path with origin=None and repopulates `_pending` so the next
        resolver tick projects the file. Returns count replayed.
        """
        if not self._wal_path.exists():
            return 0

        with self._lock:
            with self._wal_path.open("r", encoding="utf-8") as f:
                lines = [ln.rstrip("\n") for ln in f if ln.strip()]

        replayed = 0
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            system = record.get("system")
            cfg = self._systems.get(system) if system else None
            if cfg is None:
                continue
            model_cls = cfg.models.get(record.get("model"))
            if model_cls is None:
                continue
            try:
                elem = model_cls.model_validate(record["payload"])
            except Exception:
                log.exception("WAL entry failed validation")
                continue
            deleted = bool(record.get("deleted"))
            if not deleted and _db_matches(db, elem, record.get("payload")):
                continue
            if deleted and _db_lookup(db, elem) is None:
                continue
            try:
                if deleted:
                    db.delete(elem, origin=None)
                else:
                    db.update(elem, origin=None)
                replayed += 1
            except Exception:
                log.exception("WAL replay failed for %s", record.get("model"))

        return replayed
