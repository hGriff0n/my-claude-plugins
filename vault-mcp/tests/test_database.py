"""Tests for the system-agnostic database component."""

import sys
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database import Database, TableRef


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------

class Status(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Stats(BaseModel):
    completed: int
    pending: int


class Display(BaseModel):
    label: str
    stats: Stats


class Item(BaseModel):
    id: str
    name: str
    status: Status
    score: float
    active: bool
    tags: List[str]
    metadata: Dict[str, str]
    display: Display
    created: date
    archived_on: Optional[date] = None


class Named(BaseModel):
    name: str
    note: str


class Anon(BaseModel):
    value: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_item(id_: str = "i1", name: str = "First") -> Item:
    return Item(
        id=id_,
        name=name,
        status=Status.OPEN,
        score=1.5,
        active=True,
        tags=["a", "b"],
        metadata={"k": "v"},
        display=Display(label="L", stats=Stats(completed=2, pending=3)),
        created=date(2026, 1, 1),
    )


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def test_register_creates_flattened_table():
    db = Database()
    ref = db.register(Item)
    assert ref.name == "item"
    cols = {r[1] for r in db._conn.execute('PRAGMA table_info("item")').fetchall()}
    assert "id" in cols
    assert "display.label" in cols
    assert "display.stats.completed" in cols
    assert "display.stats.pending" in cols
    assert "tags" in cols
    assert "metadata" in cols
    assert "archived_on" in cols


def test_register_idempotent():
    db = Database()
    a = db.register(Item)
    b = db.register(Item)
    assert a is b


def test_register_with_system_tracks_tables():
    db = Database()
    ref_item = db.register(Item, system="things")
    ref_named = db.register(Named, system="things")
    db.register(Anon, system="other")
    assert db.tables("things") == [ref_item, ref_named]
    assert [t.model for t in db.tables("other")] == [Anon]
    assert db.tables("missing") == []


def test_register_unknown_system_returns_empty():
    db = Database()
    db.register(Item)  # no system
    assert db.tables("anything") == []


# ---------------------------------------------------------------------------
# update + query
# ---------------------------------------------------------------------------

def test_update_inserts_when_no_existing_row():
    db = Database()
    db.register(Item)
    item = _sample_item()
    db.update(item, item)

    rows = db.query("SELECT * FROM item")
    assert len(rows) == 1
    got = rows[0]
    assert got.id == "i1"
    assert got.name == "First"
    assert got.status is Status.OPEN
    assert got.tags == ["a", "b"]
    assert got.metadata == {"k": "v"}
    assert got.display.stats.completed == 2
    assert got.created == date(2026, 1, 1)
    assert got.archived_on is None
    assert got.active is True


def test_update_replaces_existing_row():
    db = Database()
    db.register(Item)
    original = _sample_item()
    db.update(original, original)

    updated = original.model_copy(update={"name": "Renamed", "status": Status.CLOSED})
    db.update(original, updated)

    rows = db.query("SELECT * FROM item")
    assert len(rows) == 1
    assert rows[0].name == "Renamed"
    assert rows[0].status is Status.CLOSED


def test_update_uses_id_field_not_full_equality():
    """Identity is `id`; changing other fields still locates the row."""
    db = Database()
    db.register(Item)
    a = _sample_item("i1", "A")
    db.update(a, a)

    # Same id, but key has different non-id fields than what's stored.
    stale_key = a.model_copy(update={"name": "stale", "score": 99.0})
    new = a.model_copy(update={"name": "B"})
    db.update(stale_key, new)

    rows = db.query("SELECT * FROM item")
    assert len(rows) == 1
    assert rows[0].name == "B"


def test_update_falls_back_to_name_when_no_id():
    db = Database()
    db.register(Named)
    a = Named(name="x", note="first")
    db.update(a, a)
    db.update(a, Named(name="x", note="second"))
    rows = db.query("SELECT * FROM named")
    assert len(rows) == 1
    assert rows[0].note == "second"


def test_update_errors_when_no_identity_field():
    db = Database()
    db.register(Anon)
    a = Anon(value=1)
    with pytest.raises(ValueError):
        db.update(a, a)


def test_update_errors_for_unregistered_model():
    db = Database()
    with pytest.raises(ValueError):
        db.update(Anon(value=1), Anon(value=1))


def test_update_rejects_mismatched_types():
    db = Database()
    db.register(Item)
    db.register(Named)
    with pytest.raises(TypeError):
        db.update(_sample_item(), Named(name="x", note=""))


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

def test_query_with_where_clause():
    db = Database()
    db.register(Item)
    db.update(_sample_item("i1", "A"), _sample_item("i1", "A"))
    db.update(_sample_item("i2", "B"), _sample_item("i2", "B"))
    rows = db.query("SELECT * FROM item WHERE id = 'i2'")
    assert [r.id for r in rows] == ["i2"]


def test_query_uses_dotted_columns_in_sql():
    db = Database()
    db.register(Item)
    db.update(_sample_item(), _sample_item())
    rows = db.query('SELECT * FROM item WHERE "display.stats.completed" = 2')
    assert len(rows) == 1


def test_query_unknown_table_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.query("SELECT * FROM nope")


def test_query_without_from_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.query("SELECT 1")


# ---------------------------------------------------------------------------
# Roundtrip preserves all field types
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_optional_none_and_dates():
    db = Database()
    db.register(Item)
    item = _sample_item()
    db.update(item, item)
    fetched = db.query("SELECT * FROM item")[0]
    assert fetched.archived_on is None
    assert isinstance(fetched.created, date)

    item2 = item.model_copy(update={"archived_on": date(2026, 5, 1)})
    db.update(item, item2)
    fetched2 = db.query("SELECT * FROM item")[0]
    assert fetched2.archived_on == date(2026, 5, 1)
