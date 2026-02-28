"""
Tests for cache/vault_cache.py.

Covers:
- initialize: full vault scan populates files, tasks_by_id, SQLite, efforts
- query_tasks: status filter, effort filter, stub filter, blocked filter
- get_task / get_task_file
- add_task: new task with auto-ID, section creation, subtask
- update_task: status change, tag changes, blocker mutations
- refresh_file: mtime check, re-parse on change
- effort operations: list_efforts, get_effort
- status diagnostics
- Thread safety: concurrent reads don't crash
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import threading
import pytest

from cache.vault_cache import VaultCache
from models.effort import EffortStatus


# ---------------------------------------------------------------------------
# Helpers to build a minimal vault on disk
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    """Create a sample vault with task files and efforts."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Top-level TASKS.md
    top_tasks = vault / "TASKS.md"
    top_tasks.write_text(
        "### Open\n\n"
        "- [ ] Global task 🆔 glob01 ➕ 2026-01-01 #stub\n"
        "- [ ] Another task 🆔 glob02 ➕ 2026-01-02 📅 2026-03-01\n"
        "- [ ] Scheduled task 🆔 glob04 ➕ 2026-01-03 ⏳ 2026-02-25\n"
        "- [ ] Scheduled later 🆔 glob05 ➕ 2026-01-03 ⏳ 2026-06-01\n"
        "- [ ] Task with note 🆔 glob06 ➕ 2026-01-03\n"
        "    - This note should be clean\n"
        "    - Second note line\n\n"
        "### Done\n\n"
        "- [x] Old task 🆔 glob03 ➕ 2025-12-01 ✅ 2026-01-01\n",
        encoding="utf-8",
    )

    # Active effort with tasks (including sub-tasks)
    active = vault / "efforts" / "my-project"
    active.mkdir(parents=True)
    (active / "CLAUDE.md").write_text("# my-project\n")
    (active / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Effort task A 🆔 eff001 ➕ 2026-01-10 #estimate:2h\n"
        "    - [ ] Sub A-1 with ID 🆔 sub001 ⏳ 2026-02-25\n"
        "    - [ ] Sub A-2 no ID ⏳ 2026-02-25\n"
        "    - [ ] Sub A-3 no ID no sched\n"
        "- [ ] Effort task B 🆔 eff002 ➕ 2026-01-11 ⛔ eff001\n\n"
        "### In Progress\n\n"
        "- [/] Effort task C 🆔 eff003 ➕ 2026-01-12\n",
        encoding="utf-8",
    )

    # Backlog effort
    backlog = vault / "efforts" / "__backlog" / "old-project"
    backlog.mkdir(parents=True)
    (backlog / "CLAUDE.md").write_text("# old-project\n")
    (backlog / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Backlog task 🆔 blg001 ➕ 2025-06-01\n",
        encoding="utf-8",
    )

    return vault


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_files_indexed(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, {".git", ".obsidian"})

        status = cache.status()
        assert status["files_indexed"] == 3  # top-level + effort + backlog

    def test_tasks_indexed(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        # glob01-06, eff001-003, blg001, sub001, + 2 auto-assigned (sub A-2, A-3)
        assert cache.status()["tasks_indexed"] == 13

    def test_efforts_indexed(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        assert cache.status()["efforts_indexed"] == 2  # my-project + old-project

    def test_vault_root_stored(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        assert cache.status()["vault_root"] == str(vault)

    def test_exclude_dirs_respected(self, tmp_path):
        vault = _make_vault(tmp_path)
        # Add a TASKS.md inside an excluded dir
        excluded = vault / "node_modules" / "some-package"
        excluded.mkdir(parents=True)
        (excluded / "TASKS.md").write_text("### Open\n\n- [ ] Bad 🆔 xxx001\n", encoding="utf-8")

        cache = VaultCache()
        cache.initialize(vault, {"node_modules"})

        # The excluded task should not be indexed
        assert cache.get_task("xxx001") is None


# ---------------------------------------------------------------------------
# Query tasks
# ---------------------------------------------------------------------------

class TestQueryTasks:
    @pytest.fixture
    def cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        c = VaultCache()
        c.initialize(vault, set())
        return c

    def test_query_all(self, cache):
        tasks = cache.query_tasks()
        assert len(tasks) == 13

    def test_query_by_status_open(self, cache):
        tasks = cache.query_tasks(status="open")
        assert all(t.status == "open" for t in tasks)
        ids = {t.id for t in tasks}
        assert "glob01" in ids
        assert "eff001" in ids

    def test_query_by_status_done(self, cache):
        tasks = cache.query_tasks(status="done")
        assert len(tasks) == 1
        assert tasks[0].id == "glob03"

    def test_query_by_status_in_progress(self, cache):
        tasks = cache.query_tasks(status="in-progress")
        assert len(tasks) == 1
        assert tasks[0].id == "eff003"

    def test_query_by_effort(self, cache):
        tasks = cache.query_tasks(effort="my-project")
        ids = {t.id for t in tasks}
        assert "eff001" in ids
        assert "eff002" in ids
        assert "eff003" in ids
        assert "sub001" in ids
        # Plus 2 auto-assigned sub-tasks (Sub A-2, Sub A-3)
        assert len(ids) == 6

    def test_query_stubs(self, cache):
        tasks = cache.query_tasks(stub=True)
        ids = {t.id for t in tasks}
        assert "glob01" in ids

    def test_query_non_stubs(self, cache):
        tasks = cache.query_tasks(stub=False)
        assert all(not t.is_stub for t in tasks)

    def test_query_blocked(self, cache):
        tasks = cache.query_tasks(blocked=True)
        ids = {t.id for t in tasks}
        assert "eff002" in ids

    def test_query_due_before(self, cache):
        tasks = cache.query_tasks(due_before="2026-04-01")
        ids = {t.id for t in tasks}
        assert "glob02" in ids  # due 2026-03-01

    def test_query_combined_filters(self, cache):
        tasks = cache.query_tasks(status="open", effort="my-project")
        ids = {t.id for t in tasks}
        assert "eff001" in ids
        assert "eff002" in ids
        assert "eff003" not in ids  # in-progress

    def test_query_limit(self, cache):
        tasks = cache.query_tasks(limit=2)
        assert len(tasks) == 2

    def test_query_scheduled_before(self, cache):
        tasks = cache.query_tasks(scheduled_before="2026-03-01")
        ids = {t.id for t in tasks}
        assert "glob04" in ids  # scheduled 2026-02-25
        assert "sub001" in ids  # sub-task scheduled 2026-02-25
        assert "glob05" not in ids  # scheduled 2026-06-01

    def test_query_scheduled_on(self, cache):
        tasks = cache.query_tasks(scheduled_on="2026-02-25")
        ids = {t.id for t in tasks}
        assert "glob04" in ids
        assert "sub001" in ids  # sub-task also scheduled 2026-02-25
        assert "glob05" not in ids
        # Sub A-2 (auto-assigned ID) also scheduled 2026-02-25
        titles = {t.title for t in tasks}
        assert "Sub A-2 no ID" in titles

    def test_query_scheduled_on_no_match(self, cache):
        tasks = cache.query_tasks(scheduled_on="2099-01-01")
        assert len(tasks) == 0

    def test_notes_stored_clean(self, cache):
        entry = cache.get_task("glob06")
        assert entry is not None
        task, _ = entry
        assert len(task.notes) == 2
        assert task.notes[0] == "This note should be clean"
        assert task.notes[1] == "Second note line"


# ---------------------------------------------------------------------------
# Sub-task indexing & auto-assigned IDs
# ---------------------------------------------------------------------------

class TestSubtaskIndexing:
    @pytest.fixture
    def cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        c = VaultCache()
        c.initialize(vault, set())
        return c

    def test_subtask_with_id_indexed(self, cache):
        """Sub-task with an explicit ID is queryable."""
        entry = cache.get_task("sub001")
        assert entry is not None
        task, _ = entry
        assert task.title == "Sub A-1 with ID"
        assert task.indent_level == 1

    def test_subtask_without_id_gets_real_id(self, cache):
        """Sub-tasks without explicit IDs get real 6-char hex IDs (not synthetic)."""
        all_ids = cache.get_all_task_ids()
        # All IDs should be real (no _ prefix)
        for tid in all_ids:
            assert not tid.startswith("_"), f"Found synthetic ID: {tid}"
        # There should be 13 total tasks
        assert len(all_ids) == 13

    def test_auto_id_queryable(self, cache):
        """Auto-assigned ID tasks appear in query results."""
        # Both sub A-2 and sub A-1 are scheduled on 2026-02-25
        tasks = cache.query_tasks(scheduled_on="2026-02-25")
        titles = {t.title for t in tasks}
        assert "Sub A-1 with ID" in titles
        assert "Sub A-2 no ID" in titles
        # glob04 is also scheduled on 2026-02-25
        assert "Scheduled task" in titles

    def test_auto_id_in_tags(self, cache):
        """Auto-assigned IDs are stored in task.tags['id'] so they persist."""
        # Find sub A-2 by title (it originally had no ID)
        tasks = cache.query_tasks(effort="my-project")
        sub_a2 = [t for t in tasks if t.title == "Sub A-2 no ID"]
        assert len(sub_a2) == 1
        task = sub_a2[0]
        assert task.id is not None
        assert len(task.id) == 6
        assert "id" in task.tags
        assert task.tags["id"] == task.id

    def test_auto_id_written_to_disk(self, tmp_path):
        """Auto-assigned IDs are persisted to disk."""
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "efforts" / "my-project" / "TASKS.md"
        content = tasks_file.read_text(encoding="utf-8")
        # Explicit IDs should be in file
        assert "sub001" in content
        assert "eff001" in content
        # Auto-assigned IDs should also be in the file now
        # Find the auto-assigned IDs for Sub A-2 and Sub A-3
        tasks = cache.query_tasks(effort="my-project")
        sub_a2 = [t for t in tasks if t.title == "Sub A-2 no ID"][0]
        sub_a3 = [t for t in tasks if t.title == "Sub A-3 no ID no sched"][0]
        assert sub_a2.id in content
        assert sub_a3.id in content

    def test_query_parent_id(self, cache):
        """parent_id filter returns direct children of a task."""
        children = cache.query_tasks(parent_id="eff001")
        assert len(children) == 3
        titles = {t.title for t in children}
        assert "Sub A-1 with ID" in titles
        assert "Sub A-2 no ID" in titles
        assert "Sub A-3 no ID no sched" in titles

    def test_query_parent_id_no_children(self, cache):
        """parent_id filter on a leaf task returns empty."""
        children = cache.query_tasks(parent_id="glob02")
        assert len(children) == 0

    def test_include_subtasks_expands_children(self, cache):
        """include_subtasks=True pulls in children of matched parents."""
        # eff001 has no scheduled date, but its children do.
        # Query for eff001 by effort + include_subtasks
        # This queries for eff001 specifically and expands.
        tasks = cache.query_tasks(effort="my-project", stub=False, blocked=False,
                                   status="open", include_subtasks=True)
        ids = {t.id for t in tasks}
        # eff001 should match and its children should be expanded
        assert "eff001" in ids
        assert "sub001" in ids

    def test_parent_has_children_list(self, cache):
        """Fetching a parent task includes its children in the Task object."""
        entry = cache.get_task("eff001")
        assert entry is not None
        task, _ = entry
        assert len(task.children) == 3
        child_titles = [c.title for c in task.children]
        assert "Sub A-1 with ID" in child_titles


# ---------------------------------------------------------------------------
# get_task / get_task_file
# ---------------------------------------------------------------------------

class TestGetTask:
    @pytest.fixture
    def cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        c = VaultCache()
        c.initialize(vault, set())
        return c

    def test_get_existing_task(self, cache):
        result = cache.get_task("eff001")
        assert result is not None
        task, path = result
        assert task.title == "Effort task A"

    def test_get_nonexistent_task(self, cache):
        assert cache.get_task("nonexistent") is None

    def test_get_task_file(self, cache):
        path = cache.get_task_file("glob01")
        assert path is not None
        assert path.name == "TASKS.md"

    def test_get_all_task_ids(self, cache):
        ids = cache.get_all_task_ids()
        assert len(ids) == 13
        assert "glob01" in ids
        assert "sub001" in ids
        # No synthetic IDs — all tasks have real IDs
        for tid in ids:
            assert not tid.startswith("_")


# ---------------------------------------------------------------------------
# add_task
# ---------------------------------------------------------------------------

class TestAddTask:
    def test_add_task_to_existing_file(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"
        new_task = cache.add_task(tasks_file, "Brand new task")

        assert new_task.id is not None
        assert len(new_task.id) == 6
        assert "created" in new_task.tags
        assert "stub" in new_task.tags

        # Task is now in cache
        found = cache.get_task(new_task.id)
        assert found is not None

    def test_add_task_to_section(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"
        new_task = cache.add_task(tasks_file, "Sectioned task", section="Open")

        assert new_task.section == "Open"

    def test_add_task_creates_section(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"
        new_task = cache.add_task(tasks_file, "New section task", section="Backlog")

        assert new_task.section == "Backlog"

    def test_add_subtask(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "efforts" / "my-project" / "TASKS.md"
        new_task = cache.add_task(tasks_file, "Subtask of A", parent_id="eff001")

        assert new_task.indent_level == 1
        # Parent should no longer be a stub (stub tag removed)
        parent = cache.get_task("eff001")
        assert parent is not None

    def test_add_task_writes_to_disk(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"
        new_task = cache.add_task(tasks_file, "Persisted task")

        # Read file back and verify task is there
        content = tasks_file.read_text(encoding="utf-8")
        assert new_task.id in content
        assert "Persisted task" in content


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_update_status_to_done(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("glob01", status="done")
        assert updated is not None
        assert updated.status == "done"
        assert "completed" in updated.tags

    def test_update_title(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("glob02", title="Renamed task")
        assert updated is not None
        assert updated.title == "Renamed task"

    def test_update_due(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("eff001", due="2026-06-01")
        assert updated is not None
        assert updated.tags.get("due") == "2026-06-01"

    def test_clear_due(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("glob02", due="")
        assert updated is not None
        assert "due" not in updated.tags

    def test_add_blocker(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("eff001", blocked_by=["glob01"])
        assert updated is not None
        assert updated.is_blocked

    def test_remove_blocker(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        updated = cache.update_task("eff002", unblock=["eff001"])
        assert updated is not None
        assert not updated.is_blocked

    def test_update_nonexistent_returns_none(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        result = cache.update_task("nonexistent", title="Nope")
        assert result is None

    def test_update_persists_to_disk(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        cache.update_task("glob02", title="On disk")

        content = (vault / "TASKS.md").read_text(encoding="utf-8")
        assert "On disk" in content


# ---------------------------------------------------------------------------
# Effort operations
# ---------------------------------------------------------------------------

class TestEffortOps:
    @pytest.fixture
    def cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        c = VaultCache()
        c.initialize(vault, set())
        return c

    def test_list_all_efforts(self, cache):
        efforts = cache.list_efforts()
        names = {e.name for e in efforts}
        assert names == {"my-project", "old-project"}

    def test_list_active_efforts(self, cache):
        efforts = cache.list_efforts(status="active")
        assert len(efforts) == 1
        assert efforts[0].name == "my-project"

    def test_list_backlog_efforts(self, cache):
        efforts = cache.list_efforts(status="backlog")
        assert len(efforts) == 1
        assert efforts[0].name == "old-project"

    def test_get_effort(self, cache):
        effort = cache.get_effort("my-project")
        assert effort is not None
        assert effort.status == EffortStatus.ACTIVE

    def test_get_nonexistent_effort(self, cache):
        assert cache.get_effort("nope") is None


# ---------------------------------------------------------------------------
# refresh_file
# ---------------------------------------------------------------------------

class TestRefreshFile:
    def test_refresh_picks_up_new_task(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"

        # Manually modify the file on disk (simulating external editor)
        content = tasks_file.read_text(encoding="utf-8")
        content += "\n- [ ] Externally added 🆔 ext001 ➕ 2026-02-01\n"
        tasks_file.write_text(content, encoding="utf-8")

        cache.refresh_file(tasks_file)

        assert cache.get_task("ext001") is not None

    def test_refresh_removes_deleted_task(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"

        # Rewrite without glob03
        tasks_file.write_text(
            "### Open\n\n"
            "- [ ] Global task 🆔 glob01 ➕ 2026-01-01 #stub\n"
            "- [ ] Another task 🆔 glob02 ➕ 2026-01-02 📅 2026-03-01\n",
            encoding="utf-8",
        )

        cache.refresh_file(tasks_file)

        assert cache.get_task("glob03") is None

    def test_refresh_handles_deleted_file(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        tasks_file = vault / "TASKS.md"
        tasks_file.unlink()

        cache.refresh_file(tasks_file)

        # Tasks from that file should be gone
        assert cache.get_task("glob01") is None
        assert cache.get_task("glob02") is None
        assert cache.get_task("glob03") is None


# ---------------------------------------------------------------------------
# Status diagnostics
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_keys(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        s = cache.status()
        assert "files_indexed" in s
        assert "tasks_indexed" in s
        assert "efforts_indexed" in s
        assert "last_full_scan" in s
        assert "vault_root" in s
        assert "exclude_dirs" in s


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_reads(self, tmp_path):
        """Multiple threads reading concurrently should not crash."""
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())

        errors = []

        def reader():
            try:
                for _ in range(50):
                    cache.query_tasks(status="open")
                    cache.get_task("glob01")
                    cache.list_efforts()
                    cache.status()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent read errors: {errors}"
