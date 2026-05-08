"""Tests for vault/efforts/parser.py."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from schemas.efforts import EffortStatus  # noqa: E402
from schemas.tasks import TaskStatus  # noqa: E402
from vault.efforts.parser import (  # noqa: E402
    CreateEffort,
    EffortParser,
    MoveEffort,
    REQUIRED_FILES,
)


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


def _placeholder(name: str, path: str | None = None):
    from schemas.efforts import DisplayDetails, Effort, TaskStats
    from schemas.time import TimeBlock

    return Effort(
        name=name,
        path=Path(path or f"efforts/{name}"),
        status=EffortStatus.ACTIVE,
        description="",
        time_details=TimeBlock(),
        display=DisplayDetails(
            task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
        ),
    )


class TestWriteScaffold:
    """`write(folder, [effort])` scaffolds a new effort when the folder is missing."""

    def _stub_obsidian(self):
        calls = []

        def fake(*args):
            calls.append(args)

            class Result:
                returncode = 0
                stderr = ""
                stdout = ""

            return Result()

        return calls, fake

    def test_scaffolds_three_files(self, tmp_path):
        root = _vault(tmp_path)
        target = root / "efforts" / "alpha"
        calls, fake = self._stub_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            EffortParser(root).write(target, [_placeholder("alpha")])
        path_args = sorted(
            arg[len("path="):] for call in calls for arg in call
            if isinstance(arg, str) and arg.startswith("path=")
        )
        assert path_args == ["efforts/alpha/00 README", "efforts/alpha/01 TASKS", "efforts/alpha/CLAUDE"]
        assert target.is_dir()

    def test_nests_existing_placeholder(self, tmp_path):
        root = _vault(tmp_path)
        target = root / "efforts" / "alpha"
        target.mkdir(parents=True)
        (target / "scratch.md").write_text("notes", encoding="utf-8")
        calls, fake = self._stub_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            EffortParser(root).write(target, [_placeholder("alpha")])
        assert (target / "alpha" / "scratch.md").exists()

    def test_moves_ideas_placeholder(self, tmp_path):
        root = _vault(tmp_path)
        target = root / "efforts" / "alpha"
        ideas_dir = root / "efforts" / "__ideas" / "alpha"
        ideas_dir.mkdir(parents=True)
        (ideas_dir / "draft.md").write_text("draft", encoding="utf-8")
        calls, fake = self._stub_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            EffortParser(root).write(target, [_placeholder("alpha")])
        assert (target / "alpha" / "draft.md").exists()
        assert not ideas_dir.exists()


class TestWriteRelocate:
    """`write(target, [effort])` relocates an existing folder to the new path."""

    def test_active_to_backlog(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        target = root / "efforts" / "__backlog" / "alpha"
        EffortParser(root).write(target, [_placeholder("alpha", "efforts/__backlog/alpha")])
        assert not (root / "efforts" / "alpha" / "CLAUDE.md").exists()
        assert (target / "CLAUDE.md").exists()

    def test_backlog_to_active(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "__backlog", "alpha", body="# Alpha\n")
        target = root / "efforts" / "alpha"
        EffortParser(root).write(target, [_placeholder("alpha")])
        assert (target / "CLAUDE.md").exists()
        assert not (root / "efforts" / "__backlog" / "alpha").exists()


class TestWriteArchive:
    def test_empty_elements_removes_existing_folder(self, tmp_path):
        root = _vault(tmp_path)
        folder = _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        EffortParser(root).write(folder, [])
        assert not folder.exists()

    def test_empty_elements_missing_folder_noop(self, tmp_path):
        root = _vault(tmp_path)
        EffortParser(root).write(root / "efforts" / "ghost", [])  # no error
