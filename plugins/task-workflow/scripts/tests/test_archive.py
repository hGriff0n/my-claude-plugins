#!/usr/bin/env python3
"""
Unit tests for the archive module (scripts/new/archive.py).
"""

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "new"))

import pytest
from archive import should_archive, collect_archived_tasks, archive_tasks, ensure_fresh
from cache import JSONTaskCache
from models import Task, TaskTree
from parser import parse_content, parse_file


def _make_task(title, status="done", completed_days_ago=None, **kwargs):
    """Helper to create a task with optional completion date."""
    tags = kwargs.pop('tags', {})
    if completed_days_ago is not None:
        date = (datetime.now() - timedelta(days=completed_days_ago)).date().isoformat()
        tags['completed'] = date
    return Task(title=title, status=status, tags=tags, **kwargs)


# --- should_archive ---

def test_should_archive_old_completed_task():
    task = _make_task("Old task", completed_days_ago=60)
    assert should_archive(task, older_than_days=30)


def test_should_not_archive_recent_completed_task():
    task = _make_task("Recent task", completed_days_ago=5)
    assert not should_archive(task, older_than_days=30)


def test_should_not_archive_open_task():
    task = _make_task("Open task", status="open", completed_days_ago=60)
    assert not should_archive(task, older_than_days=30)


def test_should_not_archive_without_completion_date():
    task = Task(title="No date", status="done")
    assert not should_archive(task, older_than_days=30)


def test_should_not_archive_invalid_date():
    task = Task(title="Bad date", status="done", tags={'completed': 'not-a-date'})
    assert not should_archive(task, older_than_days=30)


# --- collect_archived_tasks ---

def test_collect_separates_old_from_recent():
    old = _make_task("Old", id="t1", completed_days_ago=60)
    recent = _make_task("Recent", id="t2", completed_days_ago=5)
    still_open = Task(title="Open", id="t3", status="open")

    tree = TaskTree(tasks=[old, recent, still_open])
    archived, remaining = collect_archived_tasks(tree, older_than_days=30)

    assert len(archived) == 1
    assert archived[0].title == "Old"

    remaining_ids = {t.id for t in remaining.all_tasks()}
    assert remaining_ids == {"t2", "t3"}


def test_collect_archives_children_of_archived_parent():
    child = Task(title="Child", id="c1", status="open")
    parent = _make_task("Parent", id="p1", completed_days_ago=60, children=[child])

    tree = TaskTree(tasks=[parent])
    archived, remaining = collect_archived_tasks(tree, older_than_days=30)

    # Both parent and child are archived
    archived_titles = {t.title for t in archived}
    assert archived_titles == {"Parent", "Child"}

    # Nothing remains
    assert len(remaining.tasks) == 0


def test_collect_filters_children_independently():
    """A kept parent can have archived children."""
    old_child = _make_task("Old child", id="c1", completed_days_ago=60)
    kept_child = Task(title="Kept child", id="c2", status="open")
    parent = Task(title="Parent", id="p1", status="open", children=[old_child, kept_child])

    tree = TaskTree(tasks=[parent])
    archived, remaining = collect_archived_tasks(tree, older_than_days=30)

    assert len(archived) == 1
    assert archived[0].title == "Old child"

    # Parent kept with only the non-archived child
    assert len(remaining.tasks) == 1
    remaining_parent = remaining.tasks[0]
    assert len(remaining_parent.children) == 1
    assert remaining_parent.children[0].title == "Kept child"


def test_collect_does_not_mutate_original_tree():
    """collect_archived_tasks should not mutate the input tree."""
    old_child = _make_task("Old child", id="c1", completed_days_ago=60)
    kept_child = Task(title="Kept child", id="c2", status="open")
    parent = Task(title="Parent", id="p1", status="open", children=[old_child, kept_child])

    tree = TaskTree(tasks=[parent])
    original_child_count = len(tree.tasks[0].children)

    collect_archived_tasks(tree, older_than_days=30)

    # Original tree unchanged
    assert len(tree.tasks[0].children) == original_child_count


def test_collect_nothing_to_archive():
    task = Task(title="Open", status="open")
    tree = TaskTree(tasks=[task])

    archived, remaining = collect_archived_tasks(tree, older_than_days=30)

    assert len(archived) == 0
    assert len(remaining.tasks) == 1


# --- archive_tasks (integration with cache + files) ---

def test_archive_tasks_end_to_end():
    """Full integration: parse → cache → archive → verify files."""
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()

    tasks_content = f"""---
tags:
    - tasks
---

### Active

- [ ] Keep me 🆔 t1

### Done

- [x] Archive me 🆔 t2 ✅ {old_date}
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        archive_file = tmpdir / "TASKS-ARCHIVE.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text(tasks_content, encoding='utf-8')
        cache = JSONTaskCache(cache_file)

        result = archive_tasks(cache, tasks_file, archive_file, older_than_days=30)

        assert result["status"] == "success"
        assert result["count"] == 1

        # Archive file created with the task
        assert archive_file.exists()
        archive_text = archive_file.read_text(encoding='utf-8')
        assert "Archive me" in archive_text

        # TASKS.md no longer has the archived task
        tasks_text = tasks_file.read_text(encoding='utf-8')
        assert "Keep me" in tasks_text
        assert "Archive me" not in tasks_text

        # Cache is updated with remaining tree
        tree = cache.get_tree(tasks_file)
        assert tree is not None
        assert cache.find_task("t1") is not None
        assert cache.find_task("t2") is None


def test_archive_tasks_dry_run():
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()

    tasks_content = f"- [x] Archive me 🆔 t1 ✅ {old_date}\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        archive_file = tmpdir / "TASKS-ARCHIVE.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text(tasks_content, encoding='utf-8')
        cache = JSONTaskCache(cache_file)

        result = archive_tasks(cache, tasks_file, archive_file, older_than_days=30, dry_run=True)

        assert result["status"] == "success"
        assert result["count"] == 1
        assert "dry run" in result["message"].lower()

        # Files not modified
        assert not archive_file.exists()
        assert "Archive me" in tasks_file.read_text(encoding='utf-8')


def test_archive_nothing_to_archive():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text("- [ ] Open task 🆔 t1\n", encoding='utf-8')
        cache = JSONTaskCache(cache_file)

        result = archive_tasks(cache, tasks_file, tmpdir / "archive.md", older_than_days=30)
        assert result["count"] == 0


def test_archive_tasks_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cache = JSONTaskCache(tmpdir / ".cache.json")

        result = archive_tasks(cache, tmpdir / "missing.md", tmpdir / "archive.md", older_than_days=30)
        assert result["status"] == "error"


def test_archive_appends_to_existing_archive():
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        archive_file = tmpdir / "TASKS-ARCHIVE.md"
        cache_file = tmpdir / ".cache.json"

        # Pre-existing archive
        archive_file.write_text("# Task Archive\n\n- [x] Previously archived\n", encoding='utf-8')

        tasks_file.write_text(
            f"- [x] New archive 🆔 t1 ✅ {old_date}\n",
            encoding='utf-8',
        )
        cache = JSONTaskCache(cache_file)

        result = archive_tasks(cache, tasks_file, archive_file, older_than_days=30)

        archive_text = archive_file.read_text(encoding='utf-8')
        assert "Previously archived" in archive_text
        assert "New archive" in archive_text


def test_archive_creates_file_from_template():
    """New archive file should be copied from the template."""
    old_date = (datetime.now() - timedelta(days=60)).date().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        archive_file = tmpdir / "TASKS-ARCHIVE.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text(
            f"- [x] Done task 🆔 t1 ✅ {old_date}\n",
            encoding='utf-8',
        )
        cache = JSONTaskCache(cache_file)

        archive_tasks(cache, tasks_file, archive_file, older_than_days=30)

        archive_text = archive_file.read_text(encoding='utf-8')
        # Template frontmatter should be present
        assert "n/archive" in archive_text
        assert "# Task Archive" in archive_text
        # Archived task appended after template
        assert "Done task" in archive_text


# --- ensure_fresh ---

def test_ensure_fresh_parses_stale_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text("- [ ] Task 🆔 t1\n", encoding='utf-8')
        cache = JSONTaskCache(cache_file)

        # Not in cache yet → stale → should parse
        frontmatter, tree = ensure_fresh(cache, tasks_file)

        assert tree is not None
        assert tree.find_by_id("t1") is not None
        assert frontmatter == []

        # Now cached → not stale
        assert not cache.is_file_stale(tasks_file)


def test_ensure_fresh_returns_cached_when_not_stale():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tasks_file = tmpdir / "TASKS.md"
        cache_file = tmpdir / ".cache.json"

        tasks_file.write_text("- [ ] Task 🆔 t1\n", encoding='utf-8')
        cache = JSONTaskCache(cache_file)

        # Prime cache
        ensure_fresh(cache, tasks_file)

        # Second call should return same data from cache
        frontmatter, tree = ensure_fresh(cache, tasks_file)
        assert tree.find_by_id("t1") is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
