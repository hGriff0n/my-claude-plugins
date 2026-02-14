#!/usr/bin/env python3
"""
Unit tests for the tasks CLI (scripts/new/tasks.py).
"""

import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "new"))

import pytest
from cache import JSONTaskCache
from models import Task, TaskTree
from parser import parse_file, write_file
from tasks import (
    add_task, list_tasks, list_blockers, update_task,
    archive_cmd, cache_init, cache_refresh, file_create,
    resolve_tasks_file, _unblock_dependents, TASKS_TEMPLATE,
)
from utils import generate_task_id, parse_date, parse_duration


# --- test fixtures ---

class Args:
    """Minimal args namespace for testing CLI functions."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_env(tasks_content="- [ ] Existing 🆔 exist1\n"):
    """Create temp dir with TASKS.md and cache. Returns (tmpdir, tasks_file, cache)."""
    tmpdir = Path(tempfile.mkdtemp())
    tasks_file = tmpdir / "TASKS.md"
    tasks_file.write_text(tasks_content, encoding='utf-8')
    cache = JSONTaskCache(tmpdir / ".cache.json")
    return tmpdir, tasks_file, cache


def _cleanup(tmpdir):
    shutil.rmtree(tmpdir)


# ============================================================
# Utility tests
# ============================================================

class TestGenerateTaskId:
    def test_default_length(self):
        tid = generate_task_id()
        assert len(tid) == 6
        assert all(c in "0123456789abcdef" for c in tid)

    def test_custom_length(self):
        assert len(generate_task_id(length=10)) == 10

    def test_unique(self):
        ids = {generate_task_id() for _ in range(100)}
        assert len(ids) == 100


class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2026-03-15") == "2026-03-15"

    def test_today(self):
        assert parse_date("today") == datetime.now().date().isoformat()

    def test_tomorrow(self):
        expected = (datetime.now().date() + timedelta(days=1)).isoformat()
        assert parse_date("tomorrow") == expected

    def test_asap(self):
        assert parse_date("ASAP") == datetime.now().date().isoformat()

    def test_relative_days(self):
        expected = (datetime.now().date() + timedelta(days=3)).isoformat()
        assert parse_date("in 3 days") == expected

    def test_relative_weeks(self):
        expected = (datetime.now().date() + timedelta(weeks=2)).isoformat()
        assert parse_date("in 2 weeks") == expected

    def test_prefix_stripped(self):
        assert parse_date("by 2026-03-15") == "2026-03-15"

    def test_none_input(self):
        assert parse_date(None) is None
        assert parse_date("") is None

    def test_unparseable(self):
        assert parse_date("not a date at all") is None


class TestParseDuration:
    def test_hours(self):
        assert parse_duration("2h") == "2h"

    def test_minutes(self):
        assert parse_duration("30m") == "30m"

    def test_mixed(self):
        assert parse_duration("2h30m") == "2h30m"

    def test_fractional_hours(self):
        assert parse_duration("2.5h") == "2h30m"

    def test_words(self):
        assert parse_duration("2 hours") == "2h"

    def test_days(self):
        assert parse_duration("1d") == "1d"

    def test_none_input(self):
        assert parse_duration(None) is None
        assert parse_duration("") is None

    def test_unparseable(self):
        assert parse_duration("not a duration") is None


# ============================================================
# resolve_tasks_file
# ============================================================

def test_resolve_finds_tasks_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "TASKS.md").write_text("- [ ] Task\n", encoding='utf-8')
        assert resolve_tasks_file(cwd=root) == root / "TASKS.md"


def test_resolve_finds_01_tasks_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "01 TASKS.md").write_text("- [ ] Task\n", encoding='utf-8')
        assert resolve_tasks_file(cwd=root) == root / "01 TASKS.md"


def test_resolve_walks_up():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "TASKS.md").write_text("- [ ] Task\n", encoding='utf-8')
        child = root / "sub" / "dir"
        child.mkdir(parents=True)
        assert resolve_tasks_file(cwd=child) == root / "TASKS.md"


def test_resolve_returns_none_when_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert resolve_tasks_file(cwd=Path(tmpdir)) is None


# ============================================================
# add_task
# ============================================================

def test_add_basic_task():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="New task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        titles = [t.title for t in tree.all_tasks()]
        assert "New task" in titles
        new = [t for t in tree.all_tasks() if t.title == "New task"][0]
        assert len(new.id) == 6
        assert cache.find_task(new.id) is not None
    finally:
        _cleanup(tmpdir)


def test_add_with_due_date():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Deadline task", file=str(tasks_file), cache=cache,
            due="2026-03-15", estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Deadline task"][0]
        assert task.tags['due'] == "2026-03-15"
    finally:
        _cleanup(tmpdir)


def test_add_with_estimate():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Estimated task", file=str(tasks_file), cache=cache,
            due=None, estimate="2h30m", blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Estimated task"][0]
        assert task.tags['estimate'] == "2h30m"
    finally:
        _cleanup(tmpdir)


def test_add_with_blocker():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Blocked task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by="exist1", parent=None,
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Blocked task"][0]
        assert task.tags['b'] == "exist1"
    finally:
        _cleanup(tmpdir)


def test_add_atomic_no_stub():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Atomic task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=True, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Atomic task"][0]
        assert 'stub' not in task.tags
    finally:
        _cleanup(tmpdir)


def test_add_default_has_stub():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Stub task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Stub task"][0]
        assert 'stub' in task.tags
    finally:
        _cleanup(tmpdir)


def test_add_with_notes():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Noted task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes="Remember to test", section=None,
        ))
        _, tree = parse_file(tasks_file)
        task = [t for t in tree.all_tasks() if t.title == "Noted task"][0]
        assert "Remember to test" in task.notes
    finally:
        _cleanup(tmpdir)


def test_add_as_subtask():
    tmpdir, tasks_file, cache = _make_env("- [ ] Parent 🆔 p1 #stub\n")
    try:
        add_task(Args(
            title="Child task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent="p1",
            atomic=False, notes=None, section=None,
        ))
        _, tree = parse_file(tasks_file)
        parent = tree.find_by_id("p1")
        assert len(parent.children) == 1
        assert parent.children[0].title == "Child task"
        assert 'stub' not in parent.tags
    finally:
        _cleanup(tmpdir)


def test_add_subtask_missing_parent():
    tmpdir, tasks_file, cache = _make_env()
    try:
        with pytest.raises(SystemExit):
            add_task(Args(
                title="Orphan", file=str(tasks_file), cache=cache,
                due=None, estimate=None, blocked_by=None, parent="nonexistent",
                atomic=False, notes=None, section=None,
            ))
    finally:
        _cleanup(tmpdir)


def test_add_missing_file():
    tmpdir = Path(tempfile.mkdtemp())
    try:
        cache = JSONTaskCache(tmpdir / ".cache.json")
        with pytest.raises(SystemExit):
            add_task(Args(
                title="No file", file=str(tmpdir / "missing.md"), cache=cache,
                due=None, estimate=None, blocked_by=None, parent=None,
                atomic=False, notes=None, section=None,
            ))
    finally:
        _cleanup(tmpdir)


def test_add_preserves_frontmatter():
    content = "---\ntags:\n    - tasks\n---\n\n- [ ] Existing 🆔 exist1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        add_task(Args(
            title="New task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        text = tasks_file.read_text(encoding='utf-8')
        assert "---" in text
        assert "tags:" in text
        assert "New task" in text
    finally:
        _cleanup(tmpdir)


def test_add_preserves_sections():
    content = "---\ntags:\n    - tasks\n---\n\n### Active\n\n- [ ] Task A 🆔 a1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        add_task(Args(
            title="Task B", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        text = tasks_file.read_text(encoding='utf-8')
        assert "### Active" in text
        assert "Task A" in text
        assert "Task B" in text
    finally:
        _cleanup(tmpdir)


def test_add_with_explicit_section():
    content = "---\ntags:\n    - tasks\n---\n\n### Active\n\n- [ ] Task A 🆔 a1\n\n### Backlog\n\n- [ ] Task B 🆔 b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        add_task(Args(
            title="New backlog item", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section="Backlog",
        ))
        _, tree = parse_file(tasks_file)
        new_task = [t for t in tree.all_tasks() if t.title == "New backlog item"][0]
        assert new_task.section == "Backlog"
    finally:
        _cleanup(tmpdir)


def test_add_updates_cache():
    tmpdir, tasks_file, cache = _make_env()
    try:
        add_task(Args(
            title="Cached task", file=str(tasks_file), cache=cache,
            due=None, estimate=None, blocked_by=None, parent=None,
            atomic=False, notes=None, section=None,
        ))
        assert len(cache.get_all_task_ids()) >= 2
        tree = cache.get_tree(tasks_file)
        titles = [t.title for t in tree.all_tasks()]
        assert "Cached task" in titles
    finally:
        _cleanup(tmpdir)


# ============================================================
# list_tasks
# ============================================================

def _list_content():
    """Sample content for list tests."""
    return (
        "### Active\n\n"
        "- [ ] Open task 🆔 t1 📅 2026-02-01 #stub\n"
        "- [ ] Blocked task 🆔 t2 ⛔ t1\n"
        "    - [ ] Subtask 🆔 t3\n"
        "- [x] Done task 🆔 t4\n"
        "\n### Backlog\n\n"
        "- [ ] Backlog item 🆔 t5\n"
    )


def test_list_root_tasks(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due=None,
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Found 4 task(s)" in out
        assert "Open task" in out
        assert "Blocked task" in out
        assert "Done task" in out
        assert "Backlog item" in out
    finally:
        _cleanup(tmpdir)


def test_list_all_tasks(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=True, atomic=False, status=None, due=None,
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Found 5 task(s)" in out
        assert "Subtask" in out
    finally:
        _cleanup(tmpdir)


def test_list_atomic_tasks(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=True, status=None, due=None,
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        # Leaf tasks: Open task (leaf), Subtask (leaf), Done task (leaf), Backlog item (leaf)
        # Blocked task has a child, so it's NOT atomic
        assert "Subtask" in out
        assert "Open task" in out
        assert "Blocked task" not in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_status(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status='done', due=None,
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Found 1 task(s)" in out
        assert "Done task" in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_blocked(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due=None,
            blocked=True, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Blocked task" in out
        assert "Open task" not in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_stub(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due=None,
            blocked=False, stub=True, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Open task" in out
        assert "Done task" not in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_section(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due=None,
            blocked=False, stub=False, section="Backlog", tag=None,
        ))
        out = capsys.readouterr().out
        assert "Found 1 task(s)" in out
        assert "Backlog item" in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_tag(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due=None,
            blocked=False, stub=False, section=None, tag="stub",
        ))
        out = capsys.readouterr().out
        assert "Open task" in out
        assert "Done task" not in out
    finally:
        _cleanup(tmpdir)


def test_list_no_results(capsys):
    tmpdir, tasks_file, cache = _make_env(_list_content())
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status='in-progress', due=None,
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "No tasks found" in out
    finally:
        _cleanup(tmpdir)


def test_list_filter_by_due_overdue(capsys):
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    content = f"- [ ] Overdue 🆔 t1 📅 {yesterday}\n- [ ] No due 🆔 t2\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        list_tasks(Args(
            file=str(tasks_file), cache=cache,
            show_all=False, atomic=False, status=None, due='overdue',
            blocked=False, stub=False, section=None, tag=None,
        ))
        out = capsys.readouterr().out
        assert "Overdue" in out
        assert "No due" not in out
    finally:
        _cleanup(tmpdir)


# ============================================================
# list_blockers
# ============================================================

def test_list_blockers_shows_upstream(capsys):
    content = "- [ ] Blocker 🆔 b1\n- [ ] Blocked 🆔 b2 ⛔ b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        # Prime the cache
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        list_blockers(Args(id="b2", cache=cache))
        out = capsys.readouterr().out
        assert "is blocked by" in out
        assert "Blocker" in out
        assert "b1" in out
    finally:
        _cleanup(tmpdir)


def test_list_blockers_no_blockers(capsys):
    content = "- [ ] Free task 🆔 f1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        list_blockers(Args(id="f1", cache=cache))
        out = capsys.readouterr().out
        assert "has no blockers" in out
    finally:
        _cleanup(tmpdir)


def test_list_blockers_shows_downstream(capsys):
    content = "- [ ] Blocker 🆔 b1\n- [ ] Blocked 🆔 b2 ⛔ b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        list_blockers(Args(id="b1", cache=cache))
        out = capsys.readouterr().out
        assert "Blocks 1 task(s)" in out
        assert "Blocked" in out
    finally:
        _cleanup(tmpdir)


def test_list_blockers_task_not_found():
    tmpdir, tasks_file, cache = _make_env()
    try:
        with pytest.raises(SystemExit):
            list_blockers(Args(id="nonexistent", cache=cache))
    finally:
        _cleanup(tmpdir)


# ============================================================
# update_task
# ============================================================

def _update_args(cache, task_id, **overrides):
    """Build Args for update_task with defaults."""
    defaults = dict(
        id=task_id, cache=cache,
        status=None, due=None, estimate=None,
        blocked_by=None, unblock=None, notes=None,
        title=None, atomic=False,
    )
    defaults.update(overrides)
    return Args(**defaults)


def test_update_due_date():
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", due="2026-06-15"))

        task = cache.find_task("t1")
        assert task.tags['due'] == "2026-06-15"
        # Verify file was written
        _, tree = parse_file(tasks_file)
        assert tree.find_by_id("t1").tags['due'] == "2026-06-15"
    finally:
        _cleanup(tmpdir)


def test_update_estimate():
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", estimate="3h"))

        task = cache.find_task("t1")
        assert task.tags['estimate'] == "3h"
    finally:
        _cleanup(tmpdir)


def test_update_status_done():
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", status="done"))

        task = cache.find_task("t1")
        assert task.status == "done"
        assert 'completed' in task.tags
        assert task.tags['completed'] == datetime.now().date().isoformat()
    finally:
        _cleanup(tmpdir)


def test_update_completion_unblocks_dependents():
    content = "- [ ] Blocker 🆔 b1\n- [ ] Blocked 🆔 b2 ⛔ b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "b1", status="done"))

        # Blocker is done
        blocker = cache.find_task("b1")
        assert blocker.status == "done"

        # Blocked task should no longer be blocked
        blocked = cache.find_task("b2")
        assert not blocked.is_blocked

        # File should reflect the change
        _, tree = parse_file(tasks_file)
        b2 = tree.find_by_id("b2")
        assert not b2.is_blocked
    finally:
        _cleanup(tmpdir)


def test_update_completion_unblocks_across_files():
    """Completing a task in file A unblocks a dependent in file B."""
    tmpdir = Path(tempfile.mkdtemp())
    try:
        file_a = tmpdir / "a" / "TASKS.md"
        file_b = tmpdir / "b" / "TASKS.md"
        file_a.parent.mkdir()
        file_b.parent.mkdir()
        file_a.write_text("- [ ] Blocker 🆔 b1\n", encoding='utf-8')
        file_b.write_text("- [ ] Blocked 🆔 b2 ⛔ b1\n", encoding='utf-8')

        cache = JSONTaskCache(tmpdir / ".cache.json")
        from archive import ensure_fresh
        ensure_fresh(cache, file_a)
        ensure_fresh(cache, file_b)

        update_task(_update_args(cache, "b1", status="done"))

        # b2 should be unblocked
        blocked = cache.find_task("b2")
        assert not blocked.is_blocked

        # File B should be updated on disk
        _, tree_b = parse_file(file_b)
        assert not tree_b.find_by_id("b2").is_blocked
    finally:
        _cleanup(tmpdir)


def test_update_add_blocker():
    content = "- [ ] Task A 🆔 a1\n- [ ] Task B 🆔 b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "b1", blocked_by="a1"))

        task = cache.find_task("b1")
        assert task.is_blocked
        assert "a1" in task.blocking_ids
    finally:
        _cleanup(tmpdir)


def test_update_remove_blocker():
    content = "- [ ] Blocker 🆔 b1\n- [ ] Blocked 🆔 b2 ⛔ b1\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "b2", unblock="b1"))

        task = cache.find_task("b2")
        assert not task.is_blocked
    finally:
        _cleanup(tmpdir)


def test_update_title():
    tmpdir, tasks_file, cache = _make_env("- [ ] Old title 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", title="New title"))

        task = cache.find_task("t1")
        assert task.title == "New title"
    finally:
        _cleanup(tmpdir)


def test_update_notes():
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", notes="Important note"))

        task = cache.find_task("t1")
        assert task.notes == ["Important note"]
    finally:
        _cleanup(tmpdir)


def test_update_atomic():
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1 #stub\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1", atomic=True))

        task = cache.find_task("t1")
        assert 'stub' not in task.tags
    finally:
        _cleanup(tmpdir)


def test_update_no_changes(capsys):
    tmpdir, tasks_file, cache = _make_env("- [ ] Task 🆔 t1\n")
    try:
        from archive import ensure_fresh
        ensure_fresh(cache, tasks_file)

        update_task(_update_args(cache, "t1"))

        out = capsys.readouterr().out
        assert "No changes made" in out
    finally:
        _cleanup(tmpdir)


def test_update_task_not_found():
    tmpdir, tasks_file, cache = _make_env()
    try:
        with pytest.raises(SystemExit):
            update_task(_update_args(cache, "nonexistent"))
    finally:
        _cleanup(tmpdir)


# ============================================================
# archive_cmd
# ============================================================

def test_archive_cmd_basic(capsys):
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()
    content = f"- [x] Old done 🆔 t1 ✅ {old_date}\n- [ ] Keep 🆔 t2\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        archive_cmd(Args(
            file=str(tasks_file), cache=cache,
            older_than=30, dry_run=False,
        ))
        out = capsys.readouterr().out
        assert "Archived 1 task(s)" in out

        # Verify file state
        text = tasks_file.read_text(encoding='utf-8')
        assert "Keep" in text
        assert "Old done" not in text

        archive_file = tmpdir / "TASKS-ARCHIVE.md"
        assert archive_file.exists()
        assert "Old done" in archive_file.read_text(encoding='utf-8')
    finally:
        _cleanup(tmpdir)


def test_archive_cmd_dry_run(capsys):
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()
    content = f"- [x] Done task 🆔 t1 ✅ {old_date}\n"
    tmpdir, tasks_file, cache = _make_env(content)
    try:
        archive_cmd(Args(
            file=str(tasks_file), cache=cache,
            older_than=30, dry_run=True,
        ))
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "Done task" in out

        # File unchanged
        assert "Done task" in tasks_file.read_text(encoding='utf-8')
        assert not (tmpdir / "TASKS-ARCHIVE.md").exists()
    finally:
        _cleanup(tmpdir)


def test_archive_cmd_nothing(capsys):
    tmpdir, tasks_file, cache = _make_env("- [ ] Open task 🆔 t1\n")
    try:
        archive_cmd(Args(
            file=str(tasks_file), cache=cache,
            older_than=30, dry_run=False,
        ))
        out = capsys.readouterr().out
        assert "No tasks to archive" in out
    finally:
        _cleanup(tmpdir)


# ============================================================
# cache_init / cache_refresh
# ============================================================

def test_cache_init_scans_vault(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        (vault / "TASKS.md").write_text("- [ ] Root 🆔 r1\n", encoding='utf-8')
        project = vault / "efforts" / "proj"
        project.mkdir(parents=True)
        (project / "TASKS.md").write_text("- [ ] Proj 🆔 p1\n", encoding='utf-8')

        cache = JSONTaskCache(vault / ".cache.json")
        cache_init(Args(vault=str(vault), exclude=[], cache=cache))

        out = capsys.readouterr().out
        assert "2 file(s) loaded" in out
        assert "2 task(s) indexed" in out
        assert cache.find_task("r1") is not None
        assert cache.find_task("p1") is not None


def test_cache_init_with_exclude(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        (vault / "TASKS.md").write_text("- [ ] Root 🆔 r1\n", encoding='utf-8')
        hidden = vault / ".obsidian"
        hidden.mkdir()
        (hidden / "TASKS.md").write_text("- [ ] Hidden 🆔 h1\n", encoding='utf-8')

        cache = JSONTaskCache(vault / ".cache.json")
        cache_init(Args(vault=str(vault), exclude=[".obsidian"], cache=cache))

        out = capsys.readouterr().out
        assert "1 file(s) loaded" in out
        assert cache.find_task("r1") is not None
        assert cache.find_task("h1") is None


def test_cache_refresh_clears_and_rebuilds(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        (vault / "TASKS.md").write_text("- [ ] Task 🆔 t1\n", encoding='utf-8')

        cache = JSONTaskCache(vault / ".cache.json")

        # Prime cache with an extra entry that won't exist after refresh
        from parser import parse_content
        _, fake_tree = parse_content("- [ ] Fake 🆔 fake1\n")
        cache.update_file(vault / "fake.md", fake_tree)
        assert cache.find_task("fake1") is not None

        # Refresh should clear fake entry and only have real data
        cache_refresh(Args(vault=str(vault), exclude=[], cache=cache))

        out = capsys.readouterr().out
        assert "Cache refreshed" in out
        assert cache.find_task("t1") is not None
        assert cache.find_task("fake1") is None


# ============================================================
# file_create
# ============================================================

def test_file_create_new(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "project" / "TASKS.md"
        file_create(Args(path=str(target), force=False))

        out = capsys.readouterr().out
        assert "Created" in out
        assert target.exists()

        content = target.read_text(encoding='utf-8')
        assert "n/tasklist" in content
        assert "### Open" in content
        today = datetime.now().date().isoformat()
        assert today in content


def test_file_create_directory_path(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "project"
        target_dir.mkdir()
        file_create(Args(path=str(target_dir), force=False))

        expected = target_dir / "TASKS.md"
        assert expected.exists()


def test_file_create_no_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "TASKS.md"
        target.write_text("existing", encoding='utf-8')

        with pytest.raises(SystemExit):
            file_create(Args(path=str(target), force=False))

        # File unchanged
        assert target.read_text(encoding='utf-8') == "existing"


def test_file_create_force_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "TASKS.md"
        target.write_text("old content", encoding='utf-8')

        file_create(Args(path=str(target), force=True))

        content = target.read_text(encoding='utf-8')
        assert "old content" not in content
        assert "### Open" in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
