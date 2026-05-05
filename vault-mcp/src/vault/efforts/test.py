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
    _NULL_DATE,
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


class TestScan:
    def test_no_efforts_dir(self, tmp_path):
        assert EffortParser(tmp_path).scan() == []

    def test_empty_efforts_dir(self, tmp_path):
        assert EffortParser(_vault(tmp_path)).scan() == []

    def test_active_effort(self, tmp_path):
        root = _vault(tmp_path)
        eff = _make_effort(root, "efforts", "alpha")
        assert EffortParser(root).scan() == [eff]

    def test_backlog_effort(self, tmp_path):
        root = _vault(tmp_path)
        eff = _make_effort(root, "efforts", "__backlog", "old")
        assert EffortParser(root).scan() == [eff]

    def test_active_and_backlog(self, tmp_path):
        root = _vault(tmp_path)
        a = _make_effort(root, "efforts", "alpha")
        b = _make_effort(root, "efforts", "__backlog", "beta")
        assert EffortParser(root).scan() == [a, b]

    def test_folder_missing_required_file_skipped(self, tmp_path):
        root = _vault(tmp_path)
        d = root / "efforts" / "incomplete"
        d.mkdir()
        (d / "CLAUDE.md").write_text("c")
        assert EffortParser(root).scan() == []

    def test_nested_below_one_level_not_an_effort(self, tmp_path):
        root = _vault(tmp_path)
        outer = _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        _make_effort(root, "efforts", "alpha", "scratch", body="# Scratch\n")
        # Only "alpha" is an effort; the nested "scratch" is ignored.
        assert EffortParser(root).scan() == [outer]

    def test_nested_backlog_not_recursed(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "__backlog", "2025", "old")
        assert EffortParser(root).scan() == []


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
        assert effort.time_details.due == _NULL_DATE
        assert effort.time_details.scheduled == _NULL_DATE

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


class TestCreate:
    def _capture_obsidian(self):
        calls = []

        def fake(*args):
            calls.append(args)
            # Materialize the file so subsequent operations see it.
            rel = args[1]
            content = args[2] if len(args) > 2 else ""
            target_path = self._vault / rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

            class Result:
                returncode = 0
                stderr = ""
                stdout = f"Created: {rel}"

            return Result()

        return calls, fake

    def test_create_scaffolds_three_files(self, tmp_path):
        root = _vault(tmp_path)
        self._vault = root
        calls, fake = self._capture_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            from schemas.efforts import (
                DisplayDetails,
                Effort,
                TaskStats,
            )
            from schemas.time import TimeBlock

            placeholder = Effort(
                name="alpha",
                path=Path("efforts/alpha"),
                status=EffortStatus.ACTIVE,
                description="",
                time_details=TimeBlock(
                    created=_NULL_DATE,
                    last_updated=_NULL_DATE,
                    due=_NULL_DATE,
                    scheduled=_NULL_DATE,
                ),
                display=DisplayDetails(
                    task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
                ),
            )
            EffortParser(root).write(placeholder, CreateEffort())

        created = sorted(call[1] for call in calls)
        assert created == sorted(f"efforts/alpha/{f}" for f in REQUIRED_FILES)
        for f in REQUIRED_FILES:
            assert (root / "efforts" / "alpha" / f).exists()

    def test_create_rejects_existing_effort(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        from schemas.efforts import DisplayDetails, Effort, TaskStats
        from schemas.time import TimeBlock

        placeholder = Effort(
            name="alpha",
            path=Path("efforts/alpha"),
            status=EffortStatus.ACTIVE,
            description="",
            time_details=TimeBlock(
                created=_NULL_DATE, last_updated=_NULL_DATE,
                due=_NULL_DATE, scheduled=_NULL_DATE,
            ),
            display=DisplayDetails(
                task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
            ),
        )
        with pytest.raises(FileExistsError):
            EffortParser(root).write(placeholder, CreateEffort())

    def test_create_nests_existing_placeholder(self, tmp_path):
        root = _vault(tmp_path)
        self._vault = root
        # Pre-existing placeholder folder with scratch content
        placeholder_dir = root / "efforts" / "alpha"
        placeholder_dir.mkdir(parents=True)
        (placeholder_dir / "scratch.md").write_text("notes", encoding="utf-8")

        calls, fake = self._capture_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            from schemas.efforts import DisplayDetails, Effort, TaskStats
            from schemas.time import TimeBlock

            placeholder = Effort(
                name="alpha",
                path=Path("efforts/alpha"),
                status=EffortStatus.ACTIVE,
                description="",
                time_details=TimeBlock(
                    created=_NULL_DATE, last_updated=_NULL_DATE,
                    due=_NULL_DATE, scheduled=_NULL_DATE,
                ),
                display=DisplayDetails(
                    task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
                ),
            )
            EffortParser(root).write(placeholder, CreateEffort())

        assert (root / "efforts" / "alpha" / "alpha" / "scratch.md").exists()
        for f in REQUIRED_FILES:
            assert (root / "efforts" / "alpha" / f).exists()

    def test_create_moves_ideas_placeholder(self, tmp_path):
        root = _vault(tmp_path)
        self._vault = root
        ideas_dir = root / "efforts" / "__ideas" / "alpha"
        ideas_dir.mkdir(parents=True)
        (ideas_dir / "draft.md").write_text("draft", encoding="utf-8")

        calls, fake = self._capture_obsidian()
        with patch("vault.efforts.parser.obsidian_cli", side_effect=fake):
            from schemas.efforts import DisplayDetails, Effort, TaskStats
            from schemas.time import TimeBlock

            placeholder = Effort(
                name="alpha",
                path=Path("efforts/alpha"),
                status=EffortStatus.ACTIVE,
                description="",
                time_details=TimeBlock(
                    created=_NULL_DATE, last_updated=_NULL_DATE,
                    due=_NULL_DATE, scheduled=_NULL_DATE,
                ),
                display=DisplayDetails(
                    task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
                ),
            )
            EffortParser(root).write(placeholder, CreateEffort())

        assert (root / "efforts" / "alpha" / "alpha" / "draft.md").exists()
        assert not ideas_dir.exists()


class TestMove:
    def _placeholder(self, name: str):
        from schemas.efforts import DisplayDetails, Effort, TaskStats
        from schemas.time import TimeBlock

        return Effort(
            name=name,
            path=Path(f"efforts/{name}"),
            status=EffortStatus.ACTIVE,
            description="",
            time_details=TimeBlock(
                created=_NULL_DATE, last_updated=_NULL_DATE,
                due=_NULL_DATE, scheduled=_NULL_DATE,
            ),
            display=DisplayDetails(
                task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
            ),
        )

    def test_active_to_backlog(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        EffortParser(root).write(self._placeholder("alpha"), MoveEffort(target="backlog"))
        assert not (root / "efforts" / "alpha" / "CLAUDE.md").exists()
        assert (root / "efforts" / "__backlog" / "alpha" / "CLAUDE.md").exists()

    def test_backlog_to_active(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "__backlog", "alpha", body="# Alpha\n")
        EffortParser(root).write(self._placeholder("alpha"), MoveEffort(target="active"))
        assert (root / "efforts" / "alpha" / "CLAUDE.md").exists()
        assert not (root / "efforts" / "__backlog" / "alpha").exists()

    def test_active_to_active_noop(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        EffortParser(root).write(self._placeholder("alpha"), MoveEffort(target="active"))
        assert (root / "efforts" / "alpha" / "CLAUDE.md").exists()

    def test_archive_active(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "alpha", body="# Alpha\n")
        EffortParser(root).write(self._placeholder("alpha"), MoveEffort(target="archive"))
        assert not (root / "efforts" / "alpha").exists()

    def test_archive_backlog(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "efforts", "__backlog", "alpha", body="# Alpha\n")
        EffortParser(root).write(self._placeholder("alpha"), MoveEffort(target="archive"))
        assert not (root / "efforts" / "__backlog" / "alpha").exists()

    def test_unknown_effort_raises(self, tmp_path):
        root = _vault(tmp_path)
        with pytest.raises(FileNotFoundError):
            EffortParser(root).write(self._placeholder("ghost"), MoveEffort(target="backlog"))
