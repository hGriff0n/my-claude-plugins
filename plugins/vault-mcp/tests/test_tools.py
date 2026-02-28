"""
Tests for api/tools.py.

Uses a real VaultCache backed by a temporary vault on disk.
Exercises the MCP tool handler functions directly (bypasses transport).
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

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


# ---------------------------------------------------------------------------
# Effort create / move tools
# ---------------------------------------------------------------------------

class TestEffortCreate:
    def test_create_new_effort(self, setup):
        """Happy path: obsidian succeeds, effort appears in cache after refresh."""
        mcp, cache, vault = setup
        efforts_dir = vault / "efforts"

        def fake_obsidian(*args):
            # Simulate CLAUDE.md creation so cache.refresh_efforts() finds the effort
            if "create" in args and any("CLAUDE.md" in a for a in args):
                new_dir = efforts_dir / "new-effort"
                new_dir.mkdir(parents=True, exist_ok=True)
                (new_dir / "CLAUDE.md").write_text("# new-effort\n", encoding="utf-8")
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=fake_obsidian):
            result = mcp.get("effort_create")(name="new-effort")
        data = json.loads(result)
        assert "error" not in data
        assert data["name"] == "new-effort"

    def test_create_duplicate_effort(self, setup):
        """Sad path: effort with same name already exists."""
        mcp, cache, vault = setup
        result = mcp.get("effort_create")(name="side-project")
        data = json.loads(result)
        assert "error" in data
        assert "already exists" in data["error"]

    def test_create_obsidian_failure(self, setup):
        """Sad path: obsidian CLI returns non-zero exit code."""
        mcp, cache, vault = setup
        with patch("api.effort_handlers._obsidian", return_value=Mock(returncode=1, stderr="template not found")):
            result = mcp.get("effort_create")(name="fail-effort")
        data = json.loads(result)
        assert "error" in data


class TestEffortMove:
    def test_move_to_backlog(self, setup):
        """Happy path: active effort moved to __backlog/."""
        mcp, cache, vault = setup
        efforts_dir = vault / "efforts"

        def fake_obsidian(*args):
            if "move" in args:
                # Simulate moving CLAUDE.md to backlog
                backlog_dir = efforts_dir / "__backlog" / "side-project"
                backlog_dir.mkdir(parents=True, exist_ok=True)
                (backlog_dir / "CLAUDE.md").write_text("# side-project\n", encoding="utf-8")
                claude_active = efforts_dir / "side-project" / "CLAUDE.md"
                if claude_active.exists():
                    claude_active.unlink()
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=fake_obsidian):
            result = mcp.get("effort_move")(name="side-project", backlog=True, archive=False)
        data = json.loads(result)
        assert "error" not in data

    def test_activate_backlog_effort(self, setup):
        """Happy path: backlog effort moved to active."""
        mcp, cache, vault = setup
        efforts_dir = vault / "efforts"

        def fake_obsidian(*args):
            if "move" in args:
                active_dir = efforts_dir / "archived"
                active_dir.mkdir(parents=True, exist_ok=True)
                (active_dir / "CLAUDE.md").write_text("# archived\n", encoding="utf-8")
                old_claude = efforts_dir / "__backlog" / "archived" / "CLAUDE.md"
                if old_claude.exists():
                    old_claude.unlink()
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=fake_obsidian):
            result = mcp.get("effort_move")(name="archived", backlog=False, archive=False)
        data = json.loads(result)
        assert "error" not in data

    def test_move_nonexistent_effort(self, setup):
        """Sad path: effort not found in cache."""
        mcp, cache, vault = setup
        result = mcp.get("effort_move")(name="nonexistent", backlog=True, archive=False)
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]

    def test_move_active_to_active_rejected(self, setup):
        """Sad path: activating an already-active effort is rejected."""
        mcp, cache, vault = setup
        result = mcp.get("effort_move")(name="side-project", backlog=False, archive=False)
        data = json.loads(result)
        assert "error" in data
        assert "not in backlog" in data["error"]

    def test_move_backlog_to_backlog_rejected(self, setup):
        """Sad path: backlogging an already-backlog effort is rejected."""
        mcp, cache, vault = setup
        result = mcp.get("effort_move")(name="archived", backlog=True, archive=False)
        data = json.loads(result)
        assert "error" in data
        assert "not active" in data["error"]

    def test_archive_effort(self, setup):
        """Happy path: archive removes effort from tracking."""
        mcp, cache, vault = setup
        # Mock succeeds; __archive/ location won't be scanned so effort disappears
        with patch("api.effort_handlers._obsidian", return_value=Mock(returncode=0, stderr="")):
            result = mcp.get("effort_move")(name="side-project", backlog=False, archive=True)
        data = json.loads(result)
        assert "error" not in data
        assert data.get("archived") is True or data.get("name") == "side-project"

    def test_move_partial_failure(self, setup):
        """Sad path: obsidian move returns failure for some files."""
        mcp, cache, vault = setup
        with patch("api.effort_handlers._obsidian", return_value=Mock(returncode=1, stderr="failed")):
            result = mcp.get("effort_move")(name="side-project", backlog=True, archive=False)
        data = json.loads(result)
        assert "error" in data
        assert "failed to move" in data["error"]

    def test_move_visits_nested_subdirectory_files(self, setup):
        """
        Files in subdirectories of the effort are included in the move calls.

        Adds a nested file under side-project/assets/logo.png and verifies
        that _obsidian is called with its vault-relative path (not just top-level
        files), confirming the iterative DFS walks into subdirectories.
        """
        mcp, cache, vault = setup
        efforts_dir = vault / "efforts"

        # Create a nested file inside the effort
        assets = efforts_dir / "side-project" / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        nested_file = assets / "logo.png"
        nested_file.write_bytes(b"")

        moved_paths = []

        def capture_obsidian(*args):
            if "move" in args:
                # Record the path= argument value
                for arg in args:
                    if arg.startswith("path="):
                        moved_paths.append(arg[len("path="):])
            return Mock(returncode=0, stderr="")

        with patch("api.effort_handlers._obsidian", side_effect=capture_obsidian):
            result = mcp.get("effort_move")(name="side-project", backlog=True, archive=False)

        data = json.loads(result)
        assert "error" not in data

        # The nested file must appear among the moved paths
        nested_rel = str(nested_file.relative_to(vault))
        assert any(nested_rel in p or "logo.png" in p for p in moved_paths), (
            f"Expected nested file in moved paths, got: {moved_paths}"
        )


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
