"""Tests for vault/efforts/parser.py."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from schemas.efforts import EffortStatus  # noqa: E402
from schemas.tasks import TaskStatus  # noqa: E402
from vault.efforts.parser import EffortParser  # noqa: E402


def _make_effort(root: Path, *parts: str, frontmatter: str = "", body: str = "") -> Path:
    folder = root.joinpath(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    readme = folder / "00 README.md"
    if frontmatter:
        readme.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    else:
        readme.write_text(body, encoding="utf-8")
    (folder / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    (folder / "01 TASKS.md").write_text("tasks\n", encoding="utf-8")
    return folder


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "efforts").mkdir()
    return tmp_path


class TestParse:
    def test_active_status_and_path(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "alpha", body="# Alpha\n\nDesc.\n")
        [effort] = EffortParser(root).parse(folder)
        assert effort.name == "alpha"
        assert effort.path.as_posix() == "efforts/alpha"
        assert effort.status == EffortStatus.ACTIVE

    def test_backlog_status(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "__backlog", "old", body="# Old\n\nDesc.\n")
        [effort] = EffortParser(root).parse(folder)
        assert effort.status == EffortStatus.BACKLOG
        assert effort.path.as_posix() == "efforts/__backlog/old"

    def test_description_from_first_paragraph_after_title(self, tmp_path):
        root = _vault(tmp_path)
        body = "# Alpha\n\nFirst paragraph line one.\nLine two.\n\nSecond paragraph.\n"
        folder = _make_effort(root, "efforts", "alpha", body=body)
        [effort] = EffortParser(root).parse(folder)
        assert effort.description == "First paragraph line one. Line two."

    def test_description_skips_frontmatter(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(
            root,
            "efforts",
            "alpha",
            frontmatter="due: 2026-06-01",
            body="# Alpha\n\nThe goal.\n",
        )
        [effort] = EffortParser(root).parse(folder)
        assert effort.description == "The goal."

    def test_description_empty_when_no_body(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        [effort] = EffortParser(root).parse(folder)
        assert effort.description == ""

    def test_due_and_scheduled_from_frontmatter(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(
            root,
            "efforts",
            "alpha",
            frontmatter="due: 2026-06-01\nscheduled: 2026-05-15",
            body="# Alpha\n\nDesc.\n",
        )
        [effort] = EffortParser(root).parse(folder)
        assert effort.time_details.due == date(2026, 6, 1)
        assert effort.time_details.scheduled == date(2026, 5, 15)

    def test_due_and_scheduled_default_when_missing(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "alpha", body="# Alpha\n\nDesc.\n")
        [effort] = EffortParser(root).parse(folder)
        assert effort.time_details.due is None
        assert effort.time_details.scheduled is None

    def test_zero_task_stats(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "alpha", body="# Alpha\n\nDesc.\n")
        [effort] = EffortParser(root).parse(folder)
        assert effort.display.task_stats.num_by_status == {
            s.value: 0 for s in TaskStatus
        }

    def test_non_effort_folder_returns_empty(self, tmp_path):
        root = _vault(tmp_path)
        d = root / "efforts" / "incomplete"
        d.mkdir()
        (d / "CLAUDE.md").write_text("c")
        assert EffortParser(root).parse(d) == []

