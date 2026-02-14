#!/usr/bin/env python3
"""
Unit tests for the cache layer (scripts/new/cache.py).
"""

import sys
import time
import tempfile
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "new"))

import pytest
from cache import JSONTaskCache, create_cache
from parser import parse_content, parse_file
from models import Task


def test_cache_update_and_find():
    """Test cache update and task lookup."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = JSONTaskCache(cache_path)

        # Create a task tree
        content = """
- [ ] Task 1 🆔 abc123
- [ ] Task 2 🆔 def456
    - [ ] Subtask 🆔 sub1
"""
        _, tree = parse_content(content)
        file_path = Path("test.md")

        # Update cache
        cache.update_file(file_path, tree)

        # Find tasks
        task1 = cache.find_task("abc123")
        assert task1 is not None
        assert task1.title == "Task 1"
        assert task1.id == "abc123"

        task2 = cache.find_task("def456")
        assert task2 is not None
        assert task2.title == "Task 2"

        subtask = cache.find_task("sub1")
        assert subtask is not None
        assert subtask.title == "Subtask"

        # Find files
        assert cache.find_file("abc123") == file_path
        assert cache.find_file("sub1") == file_path

        # Get all IDs
        all_ids = cache.get_all_task_ids()
        assert set(all_ids) == {"abc123", "def456", "sub1"}

    finally:
        cache_path.unlink()


def test_cache_file_staleness():
    """Test cache staleness detection."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write("- [ ] Task 🆔 t1")
        tasks_path = Path(f.name)

    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = JSONTaskCache(cache_path)

        # File is stale initially (not in cache)
        assert cache.is_file_stale(tasks_path)

        # Parse and cache
        _, tree = parse_file(tasks_path)
        cache.update_file(tasks_path, tree)

        # File is no longer stale
        assert not cache.is_file_stale(tasks_path)

        # Modify file
        time.sleep(0.01)  # Ensure mtime changes
        tasks_path.write_text("- [ ] Updated task 🆔 t1", encoding='utf-8')

        # File is stale again
        assert cache.is_file_stale(tasks_path)

    finally:
        tasks_path.unlink()
        cache_path.unlink()


def test_cache_clear():
    """Test cache clearing."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = JSONTaskCache(cache_path)

        # Add data
        content = "- [ ] Task 🆔 abc123"
        _, tree = parse_content(content)
        cache.update_file(Path("test.md"), tree)

        assert len(cache.get_all_task_ids()) == 1

        # Clear
        cache.clear()

        assert len(cache.get_all_task_ids()) == 0
        assert cache.find_task("abc123") is None

    finally:
        cache_path.unlink()


def test_cache_update_replaces_old_tasks():
    """Test that updating a file replaces old task entries."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = JSONTaskCache(cache_path)
        file_path = Path("test.md")

        # Initial tasks
        content1 = """
- [ ] Task 1 🆔 t1
- [ ] Task 2 🆔 t2
"""
        _, tree1 = parse_content(content1)
        cache.update_file(file_path, tree1)

        assert cache.find_task("t1") is not None
        assert cache.find_task("t2") is not None

        # Update with different tasks
        content2 = """
- [ ] Task 3 🆔 t3
"""
        _, tree2 = parse_content(content2)
        cache.update_file(file_path, tree2)

        # Old tasks should be gone
        assert cache.find_task("t1") is None
        assert cache.find_task("t2") is None

        # New task should be present
        assert cache.find_task("t3") is not None

    finally:
        cache_path.unlink()


def test_cache_multiple_files():
    """Test cache with multiple files."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = JSONTaskCache(cache_path)

        # Add tasks from file 1
        content1 = "- [ ] Task 1 🆔 t1"
        _, tree1 = parse_content(content1)
        file1 = Path("file1.md")
        cache.update_file(file1, tree1)

        # Add tasks from file 2
        content2 = "- [ ] Task 2 🆔 t2"
        _, tree2 = parse_content(content2)
        file2 = Path("file2.md")
        cache.update_file(file2, tree2)

        # Both tasks should be findable
        assert cache.find_task("t1") is not None
        assert cache.find_task("t2") is not None

        # Find correct files
        assert cache.find_file("t1") == file1
        assert cache.find_file("t2") == file2

        # All IDs
        assert set(cache.get_all_task_ids()) == {"t1", "t2"}

    finally:
        cache_path.unlink()


def test_cache_factory():
    """Test cache factory function."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        cache = create_cache(cache_path)
        assert isinstance(cache, JSONTaskCache)

        # Verify it works
        content = "- [ ] Task 🆔 t1"
        _, tree = parse_content(content)
        cache.update_file(Path("test.md"), tree)

        task = cache.find_task("t1")
        assert task is not None
        assert task.title == "Task"

    finally:
        cache_path.unlink()


def test_cache_persistence():
    """Test that cache persists across instances."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        cache_path = Path(f.name)

    try:
        # Create cache and add data
        cache1 = JSONTaskCache(cache_path)
        content = "- [ ] Task 🆔 abc123"
        _, tree = parse_content(content)
        cache1.update_file(Path("test.md"), tree)

        # Create new cache instance (should load from disk)
        cache2 = JSONTaskCache(cache_path)
        task = cache2.find_task("abc123")
        assert task is not None
        assert task.title == "Task"

    finally:
        cache_path.unlink()


def test_scan_vault_finds_tasks_files():
    """Test that scan_vault discovers and loads TASKS.md files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        cache_path = vault / ".cache.json"

        # Create a vault structure with tasks files
        (vault / "TASKS.md").write_text("- [ ] Root task 🆔 r1\n", encoding='utf-8')

        project = vault / "efforts" / "project-a"
        project.mkdir(parents=True)
        (project / "TASKS.md").write_text("- [ ] Project task 🆔 p1\n", encoding='utf-8')

        alt = vault / "areas" / "alt"
        alt.mkdir(parents=True)
        (alt / "01 TASKS.md").write_text("- [ ] Alt task 🆔 a1\n", encoding='utf-8')

        # Non-tasks file should be ignored
        (vault / "README.md").write_text("# Not a tasks file\n", encoding='utf-8')

        cache = JSONTaskCache(cache_path)
        count = cache.scan_vault(vault)

        assert count == 3
        assert cache.find_task("r1") is not None
        assert cache.find_task("p1") is not None
        assert cache.find_task("a1") is not None


def test_scan_vault_excludes_directories():
    """Test that scan_vault respects the exclude list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        cache_path = vault / ".cache.json"

        (vault / "TASKS.md").write_text("- [ ] Root 🆔 r1\n", encoding='utf-8')

        hidden = vault / ".obsidian"
        hidden.mkdir()
        (hidden / "TASKS.md").write_text("- [ ] Hidden 🆔 h1\n", encoding='utf-8')

        templates = vault / "templates"
        templates.mkdir()
        (templates / "TASKS.md").write_text("- [ ] Template 🆔 t1\n", encoding='utf-8')

        cache = JSONTaskCache(cache_path)
        count = cache.scan_vault(vault, exclude_dirs=[".obsidian", "templates"])

        assert count == 1
        assert cache.find_task("r1") is not None
        assert cache.find_task("h1") is None
        assert cache.find_task("t1") is None


def test_scan_vault_skips_fresh_files():
    """Test that scan_vault doesn't re-parse files that are already cached."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        cache_path = vault / ".cache.json"

        (vault / "TASKS.md").write_text("- [ ] Task 🆔 t1\n", encoding='utf-8')

        cache = JSONTaskCache(cache_path)

        # First scan: parses and caches
        cache.scan_vault(vault)
        assert cache.find_task("t1") is not None

        # Second scan: file is not stale, should still report it
        count = cache.scan_vault(vault)
        assert count == 1
        assert cache.find_task("t1") is not None


def test_scan_vault_clear_and_rebuild():
    """Test clear() + scan_vault() for full rebuild."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        cache_path = vault / ".cache.json"

        (vault / "TASKS.md").write_text("- [ ] Task 🆔 t1\n", encoding='utf-8')

        cache = JSONTaskCache(cache_path)
        cache.scan_vault(vault)
        assert cache.find_task("t1") is not None

        # Clear and rebuild
        cache.clear()
        assert cache.find_task("t1") is None

        cache.scan_vault(vault)
        assert cache.find_task("t1") is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
