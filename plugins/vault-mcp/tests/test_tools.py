"""
Tests for tools/task_tools.py and tools/effort_tools.py.

Uses a real VaultCache backed by a temporary vault on disk.
Exercises the MCP tool handler functions directly (bypasses transport).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from cache.vault_cache import VaultCache
from tools.task_tools import register_task_tools
from tools.effort_tools import register_effort_tools


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
    register_task_tools(mcp, cache)
    register_effort_tools(mcp, cache)

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


class TestEffortFocus:
    def test_focus_and_get(self, setup):
        mcp, cache, vault = setup
        mcp.get("effort_focus")(name="side-project")

        result = mcp.get("effort_get_focus")()
        data = json.loads(result)
        # When focused, effort_get_focus returns _effort_to_dict which has "name"
        assert data["name"] == "side-project"
        assert data["is_focused"] is True

    def test_unfocus(self, setup):
        mcp, cache, vault = setup
        mcp.get("effort_focus")(name="side-project")
        mcp.get("effort_unfocus")()

        result = mcp.get("effort_get_focus")()
        data = json.loads(result)
        # When unfocused, effort_get_focus returns {"focused": None}
        assert data["focused"] is None
