"""
Tests for parsers/effort_scanner.py.

Covers:
- Active efforts discovered (top-level dirs with CLAUDE.md)
- Backlog efforts discovered (under __backlog/)
- Skipped names (__ideas, dashboard.base)
- Dirs without CLAUDE.md not treated as efforts
- tasks_file resolution (TASKS.md / 01 TASKS.md)
- Nested backlog dirs
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import tempfile
import pytest

from models.effort import EffortStatus
from parsers.effort_scanner import is_effort_dir, scan_efforts


def _make_effort(root: Path, name: str) -> Path:
    """Create an effort dir with CLAUDE.md marker."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "CLAUDE.md").write_text(f"# {name}\n")
    return d


def _make_dir(root: Path, name: str) -> Path:
    """Create a plain dir without CLAUDE.md."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestIsEffortDir:
    def test_returns_true_with_claude_md(self, tmp_path):
        d = _make_effort(tmp_path, "my-effort")
        assert is_effort_dir(d) is True

    def test_returns_false_without_claude_md(self, tmp_path):
        d = _make_dir(tmp_path, "not-an-effort")
        assert is_effort_dir(d) is False

    def test_returns_false_for_file(self, tmp_path):
        f = tmp_path / "somefile.md"
        f.write_text("hello")
        assert is_effort_dir(f) is False


class TestScanEfforts:
    def test_empty_efforts_dir(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        result = scan_efforts(efforts_root)
        assert result == {}

    def test_nonexistent_efforts_dir(self, tmp_path):
        result = scan_efforts(tmp_path / "efforts")
        assert result == {}

    def test_single_active_effort(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "my-project")

        result = scan_efforts(efforts_root)
        assert "my-project" in result
        assert result["my-project"].status == EffortStatus.ACTIVE

    def test_multiple_active_efforts(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "alpha")
        _make_effort(efforts_root, "beta")
        _make_effort(efforts_root, "gamma")

        result = scan_efforts(efforts_root)
        assert set(result.keys()) == {"alpha", "beta", "gamma"}
        for effort in result.values():
            assert effort.status == EffortStatus.ACTIVE

    def test_dir_without_claude_md_skipped(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "real-effort")
        _make_dir(efforts_root, "not-an-effort")

        result = scan_efforts(efforts_root)
        assert "real-effort" in result
        assert "not-an-effort" not in result

    def test_skip_ideas(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "__ideas")

        result = scan_efforts(efforts_root)
        assert "__ideas" not in result

    def test_skip_dashboard_base(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "dashboard.base")

        result = scan_efforts(efforts_root)
        assert "dashboard.base" not in result

    def test_backlog_effort(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        backlog = efforts_root / "__backlog"
        backlog.mkdir(parents=True)
        _make_effort(backlog, "old-project")

        result = scan_efforts(efforts_root)
        assert "old-project" in result
        assert result["old-project"].status == EffortStatus.BACKLOG

    def test_backlog_and_active_mixed(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        backlog = efforts_root / "__backlog"
        backlog.mkdir(parents=True)
        _make_effort(efforts_root, "active-one")
        _make_effort(backlog, "old-one")

        result = scan_efforts(efforts_root)
        assert result["active-one"].status == EffortStatus.ACTIVE
        assert result["old-one"].status == EffortStatus.BACKLOG

    def test_nested_backlog(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        nested_backlog = efforts_root / "__backlog" / "2025"
        nested_backlog.mkdir(parents=True)
        _make_effort(nested_backlog, "archived-effort")

        result = scan_efforts(efforts_root)
        assert "archived-effort" in result
        assert result["archived-effort"].status == EffortStatus.BACKLOG

    def test_effort_name_from_dirname(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "my-feature-effort")

        result = scan_efforts(efforts_root)
        effort = result["my-feature-effort"]
        assert effort.name == "my-feature-effort"
        assert effort.path == efforts_root / "my-feature-effort"

    def test_tasks_file_detected_tasks_md(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        e = _make_effort(efforts_root, "with-tasks")
        (e / "TASKS.md").write_text("### Open\n\n")

        result = scan_efforts(efforts_root)
        assert result["with-tasks"].tasks_file is not None
        assert result["with-tasks"].tasks_file.name == "TASKS.md"

    def test_tasks_file_detected_01_tasks_md(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        e = _make_effort(efforts_root, "with-numbered-tasks")
        (e / "01 TASKS.md").write_text("### Open\n\n")

        result = scan_efforts(efforts_root)
        assert result["with-numbered-tasks"].tasks_file is not None
        assert result["with-numbered-tasks"].tasks_file.name == "01 TASKS.md"

    def test_no_tasks_file_is_none(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "no-tasks")

        result = scan_efforts(efforts_root)
        assert result["no-tasks"].tasks_file is None

    def test_is_focused_defaults_false(self, tmp_path):
        efforts_root = tmp_path / "efforts"
        efforts_root.mkdir()
        _make_effort(efforts_root, "my-proj")

        result = scan_efforts(efforts_root)
        # scanner does not set focus — that's the cache's job
        assert result["my-proj"].is_focused is False
