"""
System-agnostic database component.

Every system registers its schema-derived pydantic types as tables here.
Surface: `register`, `query`, `update`, plus `tables(system)` for system-scoped
discovery. Field flattening: nested BaseModels become dotted columns; lists/
dicts become JSON columns; enums store their string value.
"""

from __future__ import annotations

import re
import sqlite3
import types
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter


@dataclass(frozen=True)
class TableRef:
    name: str
    model: Type[BaseModel]


class Database:
    """Single, system-agnostic SQLite-backed store."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._by_name: Dict[str, TableRef] = {}
        self._by_model: Dict[Type[BaseModel], TableRef] = {}
        self._systems: Dict[str, List[TableRef]] = {}
        self._model_to_system: Dict[Type[BaseModel], str] = {}
        self._debouncer: Any = None

    def attach_debouncer(self, debouncer: Any) -> None:
        """Register the write debouncer so updates can enqueue backports."""
        self._debouncer = debouncer

    # ------------------------------------------------------------------
    # Surface
    # ------------------------------------------------------------------

    def register(
        self, model: Type[BaseModel], *, system: Optional[str] = None
    ) -> TableRef:
        """Create a flattened table for `model`. Idempotent per model."""
        existing = self._by_model.get(model)
        if existing is not None:
            if system and existing not in self._systems.get(system, []):
                self._systems.setdefault(system, []).append(existing)
            return existing

        table = _table_name(model)
        columns = _flatten_columns(model)
        col_defs = ", ".join(f'"{n}" {t}' for n, t in columns)
        self._conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
        self._conn.commit()

        ref = TableRef(name=table, model=model)
        self._by_name[table] = ref
        self._by_model[model] = ref
        if system:
            self._systems.setdefault(system, []).append(ref)
            self._model_to_system[model] = system
        return ref

    def query(self, sql: str) -> List[Any]:
        """Run raw SQL; deserialize rows into the registered model.

        Type is inferred from the SQL's `FROM <table>` clause; JOINs and CTEs
        are out of scope for this signature.
        """
        ref = self._table_from_sql(sql)
        rows = self._conn.execute(sql).fetchall()
        return [_row_to_model(dict(r), ref.model) for r in rows]

    def update(self, elem: BaseModel, origin: Any = None) -> None:
        """Upsert `elem`, keyed by its identity (`id` or `name`).

        `origin` is the active `WatcherHandle` if this write is happening
        inside a watcher callback (in which case the file is already
        authoritative and no backport is enqueued), or `None` for
        DB-first edits (route handlers, scripts) where the debouncer
        schedules a backport at the owning system's lag.
        """
        self._upsert(elem)
        self._after_write(elem, origin=origin, deleted=False)

    def delete(self, elem: BaseModel, origin: Any = None) -> None:
        """Remove `elem`'s row. Same `origin` semantics as `update`."""
        ref = self._by_model.get(type(elem))
        if ref is None:
            raise ValueError(f"Model {type(elem).__name__} is not registered")
        id_field = _identity_field(type(elem))
        id_value = getattr(elem, id_field)
        self._conn.execute(
            f'DELETE FROM "{ref.name}" WHERE "{id_field}" = ?', (id_value,),
        )
        self._conn.commit()
        self._after_write(elem, origin=origin, deleted=True)

    def _upsert(self, elem: BaseModel) -> None:
        ref = self._by_model.get(type(elem))
        if ref is None:
            raise ValueError(f"Model {type(elem).__name__} is not registered")

        id_field = _identity_field(type(elem))
        id_value = getattr(elem, id_field)

        cur = self._conn.cursor()
        cur.execute(f'DELETE FROM "{ref.name}" WHERE "{id_field}" = ?', (id_value,))
        elem_row = _model_to_row(elem)
        cols = ", ".join(f'"{c}"' for c in elem_row)
        placeholders = ", ".join("?" * len(elem_row))
        cur.execute(
            f'INSERT INTO "{ref.name}" ({cols}) VALUES ({placeholders})',
            list(elem_row.values()),
        )
        self._conn.commit()

    def _after_write(
        self, elem: BaseModel, *, origin: Any, deleted: bool,
    ) -> None:
        # File-origin writes (origin is a watcher handle) are already on
        # disk — no WAL, no backport. Only DB-first writes (origin=None)
        # need the debouncer.
        if origin is not None or self._debouncer is None:
            return
        system = self._model_to_system.get(type(elem))
        if system is None:
            return
        parent = self._debouncer.parent_file(system, elem)
        if parent is None:
            return
        self._debouncer.wal_record(
            system=system, elem=elem, deleted=deleted, file=parent,
        )
        self._debouncer.enqueue(parent, system)

    def tables(self, system: str) -> List[TableRef]:
        """Return the tables a given system has registered."""
        return list(self._systems.get(system, []))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _table_from_sql(self, sql: str) -> TableRef:
        m = re.search(r'\bFROM\s+"?([A-Za-z_][\w]*)"?', sql, re.IGNORECASE)
        if not m:
            raise ValueError(f"Cannot infer table from SQL: {sql!r}")
        name = m.group(1)
        ref = self._by_name.get(name)
        if ref is None:
            raise ValueError(f"Unknown table {name!r}")
        return ref


# ---------------------------------------------------------------------------
# Schema flattening
# ---------------------------------------------------------------------------

def _table_name(model: Type[BaseModel]) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()


def _identity_field(model: Type[BaseModel]) -> str:
    fields = model.model_fields
    if "id" in fields:
        return "id"
    if "name" in fields:
        return "name"
    raise ValueError(
        f"{model.__name__} has no `id` or `name` field; cannot determine identity"
    )


def _unwrap_optional(ann: Any) -> Any:
    origin = get_origin(ann)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return ann


def _flatten_columns(model: Type[BaseModel], prefix: str = "") -> List[Tuple[str, str]]:
    cols: List[Tuple[str, str]] = []
    for name, field in model.model_fields.items():
        col = f"{prefix}.{name}" if prefix else name
        cols.extend(_columns_for(field.annotation, col))
    return cols


def _columns_for(ann: Any, col: str) -> List[Tuple[str, str]]:
    ann = _unwrap_optional(ann)
    origin = get_origin(ann)
    if origin in (list, dict, tuple, set, frozenset):
        return [(col, "TEXT")]  # JSON
    if isinstance(ann, type):
        if issubclass(ann, BaseModel):
            return _flatten_columns(ann, col)
        if issubclass(ann, Enum):
            return [(col, "TEXT")]
        if ann is bool:
            return [(col, "INTEGER")]
        if ann is int:
            return [(col, "INTEGER")]
        if ann is float:
            return [(col, "REAL")]
    return [(col, "TEXT")]


# ---------------------------------------------------------------------------
# Row serialization
# ---------------------------------------------------------------------------

def _model_to_row(instance: BaseModel, prefix: str = "") -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for name, field in type(instance).model_fields.items():
        col = f"{prefix}.{name}" if prefix else name
        val = getattr(instance, name)
        row.update(_value_to_cells(val, field.annotation, col))
    return row


def _value_to_cells(val: Any, ann: Any, col: str) -> Dict[str, Any]:
    ann = _unwrap_optional(ann)
    origin = get_origin(ann)
    if origin in (list, dict, tuple, set, frozenset):
        if val is None:
            return {col: None}
        return {col: TypeAdapter(ann).dump_json(val).decode()}
    if isinstance(val, BaseModel):
        return _model_to_row(val, col)
    if isinstance(val, Enum):
        return {col: val.value}
    if isinstance(val, bool):
        return {col: int(val)}
    if val is None or isinstance(val, (int, float, str)):
        return {col: val}
    return {col: str(val)}


# ---------------------------------------------------------------------------
# Row deserialization
# ---------------------------------------------------------------------------

def _row_to_model(row: Dict[str, Any], model: Type[BaseModel]) -> BaseModel:
    nested = _unflatten(row, model)
    return model.model_validate(nested)


def _unflatten(row: Dict[str, Any], model: Type[BaseModel]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in row.items():
        parts = key.split(".")
        ann = _resolve_annotation(model, parts)
        d = out
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = _decode_cell(value, ann)
    return out


def _resolve_annotation(model: Type[BaseModel], parts: List[str]) -> Any:
    cur: Any = model
    for p in parts:
        if isinstance(cur, type) and issubclass(cur, BaseModel):
            field = cur.model_fields.get(p)
            if field is None:
                return Any
            cur = _unwrap_optional(field.annotation)
        else:
            return cur
    return cur


def _decode_cell(value: Any, ann: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(ann)
    if origin in (list, dict, tuple, set, frozenset) and isinstance(value, str):
        return TypeAdapter(ann).validate_json(value)
    return value
