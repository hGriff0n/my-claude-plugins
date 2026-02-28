"""
Tests for api/tools.py.

Uses a real VaultCache backed by a temporary vault on disk.
Exercises the MCP tool handler functions directly (bypasses transport).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from cache.vault_cache import VaultCache
from api.tools import register_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Buy groceries 🆔 tsk001 ➕ 2026-01-01 📅 2026-02-28 #stub\n"
        "- [ ] Call dentist 🆔 tsk002 ➕ 2026-01-02 ⛔ tsk001\n\n"
        "### Done\n\n"
        "- [x] File taxes 🆔 tsk003 ➕ 2025-12-01 ✅ 2026-01-15\n",
        encoding="utf-8",
    )

    active = vault / "efforts" / "side-project"
    active.mkdir(parents=True)
    (active / "CLAUDE.md").write_text("# side-project\n")
    (active / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Set up repo 🆔 sp001 ➕ 2026-01-10\n",
        encoding="utf-8",
    )

    backlog = vault / "efforts" / "__backlog" / "archived"
    backlog.mkdir(parents=True)
    (backlog / "CLAUDE.md").write_text("# archived\n")

    return vault


class _FakeMCP:
    """Minimal fake to capture tool registrations."""

    def __init__(self):
        self._tools = {}

    def tool(self, *args, **kwargs):
        """Decorator that records functions by name."""
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator

    def get(self, name: str):
        return self._tools[name]


@pytest.fixture
def setup(tmp_path):
    vault = _make_vault(tmp_path)
    cache = VaultCache()
    cache.initialize(vault, set())

    mcp = _FakeMCP()
    register_tools(mcp, cache)

    return mcp, cache, vault


# ---------------------------------------------------------------------------
# Task tools
# ---------------------------------------------------------------------------

class TestTaskList:
    def test_list_all(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_list")(status=None, effort=None, stub=None, blocked=None)
        data = json.loads(result)
        assert len(data) >= 4  # tsk001, tsk002, tsk003, sp001

    def test_list_by_status(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_list")(status="done", effort=None, stub=None, blocked=None)
        data = json.loads(result)
        ids = {t["id"] for t in data}
        assert "tsk003" in ids

    def test_list_by_effort(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_list")(status=None, effort="side-project", stub=None, blocked=None)
        data = json.loads(result)
        ids = {t["id"] for t in data}
        assert "sp001" in ids
        assert "tsk001" not in ids

    def test_list_stubs(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_list")(status=None, effort=None, stub=True, blocked=None)
        data = json.loads(result)
        assert all(t.get("is_stub") for t in data)

    def test_list_blocked(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_list")(status=None, effort=None, stub=None, blocked=True)
        data = json.loads(result)
        ids = {t["id"] for t in data}
        assert "tsk002" in ids


class TestTaskGet:
    def test_get_existing(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_get")(task_id="tsk001")
        data = json.loads(result)
        assert data["title"] == "Buy groceries"
        assert data["status"] == "open"

    def test_get_nonexistent(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_get")(task_id="nonexistent")
        data = json.loads(result)
        assert "error" in data


class TestTaskAdd:
    def test_add_task(self, setup):
        mcp, cache, vault = setup
        tasks_file = str(vault / "TASKS.md")
        result = mcp.get("task_add")(
            file_path=tasks_file,
            title="New task from tool",
            section=None,
            parent_id=None,
        )
        data = json.loads(result)
        assert "id" in data
        assert data["title"] == "New task from tool"

        # Verify it's in cache
        found = cache.get_task(data["id"])
        assert found is not None


class TestTaskUpdate:
    def test_update_status(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_update")(
            task_id="tsk001",
            status="done",
            title=None,
            due=None,
            scheduled=None,
            estimate=None,
        )
        data = json.loads(result)
        assert data["status"] == "done"

    def test_update_title(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_update")(
            task_id="tsk002",
            title="Call doctor instead",
            status=None,
            due=None,
            scheduled=None,
            estimate=None,
        )
        data = json.loads(result)
        assert data["title"] == "Call doctor instead"


class TestTaskBlockers:
    def test_get_blockers(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("task_blockers")(task_id="tsk002")
        data = json.loads(result)
        assert "blocked_by" in data
        assert len(data["blocked_by"]) > 0
        # tsk002 is blocked by tsk001
        blocker_ids = {b["id"] for b in data["blocked_by"]}
        assert "tsk001" in blocker_ids


class TestCacheStatus:
    def test_cache_status(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("cache_status")()
        data = json.loads(result)
        assert "files_indexed" in data
        assert "tasks_indexed" in data
        assert data["tasks_indexed"] >= 4


# ---------------------------------------------------------------------------
# Effort tools
# ---------------------------------------------------------------------------

class TestEffortList:
    def test_list_all(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("effort_list")(status=None)
        data = json.loads(result)
        names = {e["name"] for e in data}
        assert "side-project" in names
        assert "archived" in names

    def test_list_active(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("effort_list")(status="active")
        data = json.loads(result)
        names = {e["name"] for e in data}
        assert "side-project" in names
        assert "archived" not in names


class TestEffortGet:
    def test_get_existing(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("effort_get")(name="side-project")
        data = json.loads(result)
        assert data["name"] == "side-project"
        assert data["status"] == "active"

    def test_get_nonexistent(self, setup):
        mcp, cache, vault = setup
        result = mcp.get("effort_get")(name="nonexistent")
        data = json.loads(result)
        assert "error" in data


class TestTaskRefs:
    def test_ref_set_on_indexed_task(self, setup):
        """Tasks read from cache should have a non-None ref."""
        _, cache, _ = setup
        task, _ = cache.get_task("tsk001")
        assert task.ref is not None

    def test_ref_updated_after_add_subtask(self, setup):
        """
        Adding a subtask to a parent inserts a new line between the parent and the
        next sibling.  After the write+reload, the sibling's ref must reflect its
        new (shifted) line number.
        """
        _, cache, vault = setup
        tasks_file = vault / "TASKS.md"

        tsk002_before, _ = cache.get_task("tsk002")
        line_before = tsk002_before.line_number

        # Adding a child under tsk001 inserts a line before tsk002
        cache.add_task(tasks_file, "Subtask of groceries", parent_id="tsk001")

        tsk002_after, _ = cache.get_task("tsk002")
        assert tsk002_after.line_number > line_before, "tsk002 should have shifted down"

        file_lines = tasks_file.read_text(encoding="utf-8").splitlines()
        assert tsk002_after.title in file_lines[tsk002_after.line_number]

    def test_ref_updated_after_add_to_earlier_section(self, setup):
        """
        Appending a task to an earlier section shifts tasks in later sections.
        After the write+reload, refs for the later tasks must be correct.
        """
        _, cache, vault = setup
        tasks_file = vault / "TASKS.md"

        tsk003_before, _ = cache.get_task("tsk003")
        line_before = tsk003_before.line_number

        # Append to Open (before Done section where tsk003 lives)
        cache.add_task(tasks_file, "New open task", section="Open")

        tsk003_after, _ = cache.get_task("tsk003")
        assert tsk003_after.line_number > line_before, "tsk003 should have shifted down"

        file_lines = tasks_file.read_text(encoding="utf-8").splitlines()
        assert tsk003_after.title in file_lines[tsk003_after.line_number]
