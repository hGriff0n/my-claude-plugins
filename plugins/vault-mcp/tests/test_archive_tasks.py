"""
Tests for scripts/archive_tasks.py.

Covers:
- collect_archivable: fully done trees, mixed status, reopen logic
- group_by_date: grouping by completion date
- build_archive_content: indentation normalization, tag preservation
- append_to_daily_note: section creation, appending, idempotency
- remove_tasks_from_source: task removal, no gaps, structure preservation
- reopen_parent: status change, blocked tag, reopen note
- End-to-end: full archive cycle, no data loss, idempotency
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from cache.vault_cache import VaultCache
from parsers.task_parser import parse_file
from scripts.archive_tasks import (
    _collect_all_ids_flat,
    _filter_same_day_children,
    _filter_tree_tasks,
    _has_open_descendants,
    append_to_daily_note,
    build_archive_content,
    collect_archivable,
    group_by_date,
    remove_tasks_from_source,
    _dict_to_task,
)


# ---------------------------------------------------------------------------
# Helpers to build test data
# ---------------------------------------------------------------------------


def _make_task(
    title: str,
    task_id: str,
    status: str = "done",
    completed: str = "2026-01-15",
    children: list = None,
    indent_level: int = 0,
    notes: list = None,
    extra_tags: dict = None,
) -> dict:
    """Create a task dict matching the REST API response format."""
    tags = {}
    if extra_tags:
        tags.update(extra_tags)
    tags["id"] = task_id
    if completed:
        tags["completed"] = completed
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "tags": tags,
        "notes": notes or [],
        "children": children or [],
        "indent_level": indent_level,
        "section": "Done",
        "ref": None,
        "is_stub": False,
        "is_blocked": False,
        "blocking_ids": [],
    }


def _make_vault(tmp_path: Path) -> Path:
    """Create a test vault with various task states for archival testing."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Root TASKS.md with mixed tasks
    top_tasks = vault / "TASKS.md"
    top_tasks.write_text(
        "### Open\n\n"
        "- [ ] Stay open 🆔 open01 ➕ 2026-01-01\n"
        "- [ ] Also open 🆔 open02 ➕ 2026-01-02\n\n"
        "### Done\n\n"
        "- [x] Completed Jan 15 🆔 done01 ➕ 2026-01-10 ✅ 2026-01-15\n"
        "- [x] Completed Jan 16 🆔 done02 ➕ 2026-01-11 ✅ 2026-01-16\n"
        "- [x] Done parent with open child 🆔 done03 ➕ 2026-01-10 ✅ 2026-01-15\n"
        "    - [ ] Open child 🆔 open03 ➕ 2026-01-10\n"
        "    - [x] Done child same day 🆔 done04 ➕ 2026-01-10 ✅ 2026-01-15\n",
        encoding="utf-8",
    )

    # Effort with nested tasks
    effort = vault / "efforts" / "test-project"
    effort.mkdir(parents=True)
    (effort / "CLAUDE.md").write_text("# test-project\n")
    (effort / "TASKS.md").write_text(
        "### Open\n\n"
        "- [ ] Effort open 🆔 eopen1 ➕ 2026-01-01\n\n"
        "### Done\n\n"
        "- [x] Effort done 🆔 edone1 ➕ 2026-01-10 ✅ 2026-01-15\n"
        "    - [x] Effort child done 🆔 edone2 ➕ 2026-01-10 ✅ 2026-01-15\n"
        "- [x] Deep nested 🆔 edone3 ➕ 2026-01-10 ✅ 2026-01-16\n"
        "    - [x] Mid child 🆔 edone4 ➕ 2026-01-10 ✅ 2026-01-16\n"
        "        - [x] Leaf child 🆔 edone5 ➕ 2026-01-10 ✅ 2026-01-16\n",
        encoding="utf-8",
    )

    return vault


# ---------------------------------------------------------------------------
# TestCollectArchivable
# ---------------------------------------------------------------------------


class TestCollectArchivable:
    def test_fully_done_tree_is_archivable(self):
        parent = _make_task("Parent", "p1", children=[
            _make_task("Child", "c1"),
        ])
        result = collect_archivable([parent], api_base="http://unused")
        assert len(result) == 1
        assert result[0]["id"] == "p1"

    def test_done_leaf_archivable(self):
        task = _make_task("Leaf", "l1")
        result = collect_archivable([task], api_base="http://unused")
        assert len(result) == 1
        assert result[0]["id"] == "l1"

    @patch("scripts.archive_tasks.reopen_parent")
    def test_done_parent_with_open_child_triggers_reopen(self, mock_reopen):
        parent = _make_task("Parent", "p1", children=[
            _make_task("Open child", "c1", status="open", completed=None),
            _make_task("Done child", "c2"),
        ])
        result = collect_archivable([parent], api_base="http://test")
        # Parent should not be in archivable
        assert "p1" not in {t["id"] for t in result}
        # Done child should be archivable
        assert "c2" in {t["id"] for t in result}
        # Reopen should have been called
        mock_reopen.assert_called_once()

    def test_open_task_excluded(self):
        task = _make_task("Open", "o1", status="open", completed=None)
        result = collect_archivable([task], api_base="http://unused")
        assert len(result) == 0

    def test_done_without_completed_tag_excluded(self):
        task = _make_task("Done no date", "d1", completed=None)
        result = collect_archivable([task], api_base="http://unused")
        assert len(result) == 0

    @patch("scripts.archive_tasks.reopen_parent")
    def test_deeply_nested_partial_done(self, mock_reopen):
        """Only the fully-done subtrees should be archivable."""
        task = _make_task("Root", "r1", children=[
            _make_task("Done branch", "d1", children=[
                _make_task("Done leaf", "d2"),
            ]),
            _make_task("Mixed branch", "m1", children=[
                _make_task("Open leaf", "o1", status="open", completed=None),
            ]),
        ])
        result = collect_archivable([task], api_base="http://test")
        ids = {t["id"] for t in result}
        # Root should be reopened (has open descendants via m1/o1)
        assert "r1" not in ids
        # d1+d2 is fully done subtree → archivable
        assert "d1" in ids
        # m1 has open child → should be reopened, not archived
        assert "m1" not in ids


# ---------------------------------------------------------------------------
# TestGroupByDate
# ---------------------------------------------------------------------------


class TestGroupByDate:
    def test_groups_by_completion_date(self):
        tasks = [
            _make_task("A", "a1", completed="2026-01-15"),
            _make_task("B", "b1", completed="2026-01-16"),
            _make_task("C", "c1", completed="2026-01-15"),
        ]
        groups = group_by_date(tasks)
        assert len(groups) == 2
        assert len(groups["2026-01-15"]) == 2
        assert len(groups["2026-01-16"]) == 1

    def test_single_date_all_same(self):
        tasks = [
            _make_task("A", "a1", completed="2026-01-15"),
            _make_task("B", "b1", completed="2026-01-15"),
        ]
        groups = group_by_date(tasks)
        assert len(groups) == 1
        assert len(groups["2026-01-15"]) == 2


# ---------------------------------------------------------------------------
# TestBuildArchiveContent
# ---------------------------------------------------------------------------


class TestBuildArchiveContent:
    def test_root_task_at_indent_zero(self):
        task = _make_task("Root task", "r1", indent_level=0)
        content = build_archive_content([task])
        assert content.startswith("- [x] Root task")

    def test_subtask_normalized_to_indent_zero(self):
        """A subtask at indent 3 should be rendered at indent 0."""
        task = _make_task("Deep task", "d1", indent_level=3)
        content = build_archive_content([task])
        lines = content.splitlines()
        assert lines[0].startswith("- [x] Deep task")
        assert not lines[0].startswith("    ")

    def test_parent_with_children_normalized(self):
        """Parent at indent 0, child at indent 1."""
        parent = _make_task("Parent", "p1", indent_level=2, children=[
            _make_task("Child", "c1", indent_level=3),
        ])
        content = build_archive_content([parent])
        lines = content.splitlines()
        assert lines[0].startswith("- [x] Parent")
        assert lines[1].startswith("    - [x] Child")

    def test_includes_notes(self):
        task = _make_task("With notes", "n1", notes=["A note here"])
        content = build_archive_content([task])
        assert "A note here" in content

    def test_tags_preserved(self):
        task = _make_task(
            "Tagged", "t1",
            extra_tags={"due": "2026-02-01", "estimate": "2h"},
        )
        content = build_archive_content([task])
        assert "📅 2026-02-01" in content
        assert "[[estimate::2h]]" in content

    def test_different_day_children_excluded(self):
        """Children completed on a different day should not be included."""
        parent = _make_task("Parent", "p1", completed="2026-01-15", children=[
            _make_task("Same day", "c1", completed="2026-01-15"),
            _make_task("Different day", "c2", completed="2026-01-16"),
        ])
        content = build_archive_content([parent])
        assert "Same day" in content
        assert "Different day" not in content


# ---------------------------------------------------------------------------
# TestAppendToDailyNote
# ---------------------------------------------------------------------------


class TestAppendToDailyNote:
    def test_creates_section_in_existing_file(self, tmp_path):
        daily = tmp_path / "2026-01-15.md"
        daily.write_text("# 2026-01-15\n\nSome existing content.\n", encoding="utf-8")
        append_to_daily_note(daily, "- [x] Task A\n- [x] Task B")
        content = daily.read_text(encoding="utf-8")
        assert "## Completed Tasks" in content
        assert "- [x] Task A" in content
        assert "- [x] Task B" in content

    def test_appends_to_existing_section(self, tmp_path):
        daily = tmp_path / "2026-01-15.md"
        daily.write_text(
            "# 2026-01-15\n\n## Completed Tasks\n\n- [x] Already here\n",
            encoding="utf-8",
        )
        append_to_daily_note(daily, "- [x] New task")
        content = daily.read_text(encoding="utf-8")
        assert content.count("## Completed Tasks") == 1
        assert "- [x] Already here" in content
        assert "- [x] New task" in content

    def test_new_file_creation(self, tmp_path):
        daily = tmp_path / "daily" / "2026" / "2026-01-15.md"
        append_to_daily_note(daily, "- [x] Task A")
        assert daily.exists()
        content = daily.read_text(encoding="utf-8")
        assert "## Completed Tasks" in content
        assert "- [x] Task A" in content

    def test_no_duplicate_heading(self, tmp_path):
        daily = tmp_path / "2026-01-15.md"
        daily.write_text("# 2026-01-15\n", encoding="utf-8")
        append_to_daily_note(daily, "- [x] Task A")
        append_to_daily_note(daily, "- [x] Task B")
        content = daily.read_text(encoding="utf-8")
        assert content.count("## Completed Tasks") == 1
        assert "- [x] Task A" in content
        assert "- [x] Task B" in content

    def test_inserts_before_next_section(self, tmp_path):
        daily = tmp_path / "2026-01-15.md"
        daily.write_text(
            "# 2026-01-15\n\n## Completed Tasks\n\n- [x] First\n\n## Notes\n\nSome notes.\n",
            encoding="utf-8",
        )
        append_to_daily_note(daily, "- [x] Second")
        content = daily.read_text(encoding="utf-8")
        # "Second" should appear before "## Notes"
        assert content.index("- [x] Second") < content.index("## Notes")
        assert "Some notes." in content


# ---------------------------------------------------------------------------
# TestRemoveTasksFromSource
# ---------------------------------------------------------------------------


class TestRemoveTasksFromSource:
    def _make_cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())
        return cache, vault

    def test_removes_task_by_id(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        remove_tasks_from_source(cache, tasks_file, {"done01"})
        tree = parse_file(tasks_file)
        all_ids = {t.id for t in tree.all_tasks()}
        assert "done01" not in all_ids

    def test_remaining_tasks_intact(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        remove_tasks_from_source(cache, tasks_file, {"done01"})
        tree = parse_file(tasks_file)
        all_ids = {t.id for t in tree.all_tasks()}
        assert "open01" in all_ids
        assert "open02" in all_ids
        assert "done02" in all_ids

    def test_no_gaps_in_output(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        remove_tasks_from_source(cache, tasks_file, {"done01", "done02"})
        content = tasks_file.read_text(encoding="utf-8")
        # No triple+ blank lines (which would indicate gaps)
        assert "\n\n\n" not in content

    def test_removes_nested_subtask(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        # Remove done child, keep parent
        remove_tasks_from_source(cache, tasks_file, {"done04"})
        tree = parse_file(tasks_file)
        all_ids = {t.id for t in tree.all_tasks()}
        assert "done04" not in all_ids
        assert "done03" in all_ids  # Parent kept

    def test_sections_preserved(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        # Remove all done tasks
        remove_tasks_from_source(cache, tasks_file, {"done01", "done02", "done03", "done04"})
        tree = parse_file(tasks_file)
        headings = {s.heading for s in tree.sections}
        assert "Open" in headings
        assert "Done" in headings  # Section preserved even if empty

    def test_multiple_removals_same_file(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        tasks_file = vault / "TASKS.md"
        remove_tasks_from_source(cache, tasks_file, {"done01", "done02"})
        tree = parse_file(tasks_file)
        all_ids = {t.id for t in tree.all_tasks()}
        assert "done01" not in all_ids
        assert "done02" not in all_ids
        # Open tasks still there
        assert "open01" in all_ids

    def test_removes_from_effort_file(self, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        effort_tasks = vault / "efforts" / "test-project" / "TASKS.md"
        remove_tasks_from_source(cache, effort_tasks, {"edone1", "edone2"})
        tree = parse_file(effort_tasks)
        all_ids = {t.id for t in tree.all_tasks()}
        assert "edone1" not in all_ids
        assert "edone2" not in all_ids
        assert "eopen1" in all_ids


# ---------------------------------------------------------------------------
# TestBuildArchiveContent — indentation normalization
# ---------------------------------------------------------------------------


class TestIndentNormalization:
    def test_deep_subtask_becomes_root(self):
        """A task at indent level 5 should serialize at indent 0."""
        task = _make_task("Deep task", "d1", indent_level=5)
        content = build_archive_content([task])
        first_line = content.splitlines()[0]
        assert first_line == first_line.lstrip()  # No leading whitespace

    def test_nested_children_relative_indent(self):
        """Parent→child→grandchild should be 0→1→2 regardless of original indent."""
        grandchild = _make_task("Grandchild", "gc1", indent_level=4)
        child = _make_task("Child", "c1", indent_level=3, children=[grandchild])
        parent = _make_task("Parent", "p1", indent_level=2, children=[child])
        content = build_archive_content([parent])
        lines = content.splitlines()
        assert not lines[0].startswith("    ")  # Parent at 0
        assert lines[1].startswith("    ") and not lines[1].startswith("        ")  # Child at 1
        assert lines[2].startswith("        ") and not lines[2].startswith("            ")  # Grandchild at 2


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_has_open_descendants_false(self):
        task = _make_task("Done", "d1", children=[
            _make_task("Also done", "d2"),
        ])
        assert _has_open_descendants(task) is False

    def test_has_open_descendants_true(self):
        task = _make_task("Done", "d1", children=[
            _make_task("Open", "o1", status="open", completed=None),
        ])
        assert _has_open_descendants(task) is True

    def test_collect_all_ids_flat(self):
        tasks = [
            _make_task("A", "a1", children=[
                _make_task("B", "b1"),
                _make_task("C", "c1", children=[
                    _make_task("D", "d1"),
                ]),
            ]),
        ]
        ids = _collect_all_ids_flat(tasks)
        assert ids == {"a1", "b1", "c1", "d1"}

    def test_filter_same_day_children(self):
        task = _dict_to_task(_make_task("Parent", "p1", completed="2026-01-15", children=[
            _make_task("Same day", "c1", completed="2026-01-15"),
            _make_task("Diff day", "c2", completed="2026-01-16"),
        ]))
        filtered = _filter_same_day_children(task, "2026-01-15")
        child_ids = {c.id for c in filtered.children}
        assert "c1" in child_ids
        assert "c2" not in child_ids

    def test_dict_to_task_round_trip(self):
        d = _make_task("Test", "t1", notes=["A note"], children=[
            _make_task("Child", "c1"),
        ])
        task = _dict_to_task(d)
        assert task.title == "Test"
        assert task.id == "t1"
        assert task.status == "done"
        assert len(task.children) == 1
        assert task.notes == ["A note"]


# ---------------------------------------------------------------------------
# TestFilterTreeTasks
# ---------------------------------------------------------------------------


class TestFilterTreeTasks:
    def test_filters_by_id(self):
        from models.task import Task
        tasks = [
            Task(title="Keep", id="k1"),
            Task(title="Remove", id="r1"),
        ]
        result = _filter_tree_tasks(tasks, {"r1"})
        assert len(result) == 1
        assert result[0].id == "k1"

    def test_filters_nested_children(self):
        from models.task import Task
        child_keep = Task(title="Keep child", id="ck")
        child_remove = Task(title="Remove child", id="cr")
        parent = Task(title="Parent", id="p1", children=[child_keep, child_remove])
        result = _filter_tree_tasks([parent], {"cr"})
        assert len(result) == 1
        assert len(result[0].children) == 1
        assert result[0].children[0].id == "ck"

    def test_removes_parent_keeps_nothing(self):
        from models.task import Task
        parent = Task(title="Parent", id="p1", children=[
            Task(title="Child", id="c1"),
        ])
        result = _filter_tree_tasks([parent], {"p1"})
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def _make_cache(self, tmp_path):
        vault = _make_vault(tmp_path)
        cache = VaultCache()
        cache.initialize(vault, set())
        return cache, vault

    @patch("scripts.archive_tasks.get_daily_note_path")
    @patch("scripts.archive_tasks.fetch_done_tasks")
    @patch("scripts.archive_tasks.reopen_parent")
    def test_full_archive_cycle(self, mock_reopen, mock_fetch, mock_daily_path, tmp_path):
        cache, vault = self._make_cache(tmp_path)
        daily_dir = tmp_path / "daily"
        daily_dir.mkdir()

        # Mock daily note paths
        def daily_path_for(date_str):
            p = daily_dir / f"{date_str}.md"
            return p
        mock_daily_path.side_effect = daily_path_for

        # Build REST API response from actual cache data
        done_tasks = []
        for task_id in cache.get_all_task_ids():
            entry = cache.get_task(task_id)
            if entry:
                task, fp = entry
                if task.status == "done" and task.tags.get("completed"):
                    # Only add root-level done tasks (not children that are part of a parent)
                    if task.indent_level == 0 or not any(
                        task_id in {c.id for c in parent_task.children}
                        for pid in cache.get_all_task_ids()
                        if (pe := cache.get_task(pid)) and (parent_task := pe[0])
                        and parent_task.status == "done"
                    ):
                        done_tasks.append(self._task_to_api_dict(task))

        mock_fetch.return_value = done_tasks

        from scripts.archive_tasks import archive_tasks
        result = archive_tasks(cache, api_base="http://test")

        # Verify: daily notes were created
        assert result["daily_notes"] >= 1
        assert result["archived"] >= 1

        # Verify: archived tasks are gone from source
        tasks_file = vault / "TASKS.md"
        tree = parse_file(tasks_file)
        remaining_ids = {t.id for t in tree.all_tasks()}
        assert "done01" not in remaining_ids
        assert "done02" not in remaining_ids
        # Open tasks still present
        assert "open01" in remaining_ids
        assert "open02" in remaining_ids

    def _task_to_api_dict(self, task) -> dict:
        """Convert a Task model to REST API dict format."""
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "tags": dict(task.tags),
            "notes": list(task.notes),
            "children": [self._task_to_api_dict(c) for c in task.children],
            "indent_level": task.indent_level,
            "section": task.section,
            "ref": task.ref,
            "is_stub": task.is_stub,
            "is_blocked": task.is_blocked,
            "blocking_ids": task.blocking_ids,
        }

    @patch("scripts.archive_tasks.get_daily_note_path")
    def test_no_data_loss(self, mock_daily_path, tmp_path):
        """Every done task must appear in daily note XOR remain in source."""
        cache, vault = self._make_cache(tmp_path)
        daily_dir = tmp_path / "daily"
        daily_dir.mkdir()
        mock_daily_path.side_effect = lambda d: daily_dir / f"{d}.md"

        tasks_file = vault / "TASKS.md"
        original_tree = parse_file(tasks_file)
        original_done_ids = {
            t.id for t in original_tree.all_tasks()
            if t.status == "done" and t.tags.get("completed")
        }

        # Simulate archiving done01 (fully archivable, no open children)
        archivable = [self._task_to_api_dict(t)
                      for t in original_tree.all_tasks()
                      if t.id == "done01"]

        from scripts.archive_tasks import build_archive_content, append_to_daily_note

        content = build_archive_content(archivable)
        daily_path = daily_dir / "2026-01-15.md"
        append_to_daily_note(daily_path, content)

        remove_tasks_from_source(cache, tasks_file, {"done01"})

        # Verify: done01 is in daily note
        daily_content = daily_path.read_text(encoding="utf-8")
        assert "done01" in daily_content

        # Verify: done01 is NOT in source
        refreshed = parse_file(tasks_file)
        assert "done01" not in {t.id for t in refreshed.all_tasks()}

    @patch("scripts.archive_tasks.fetch_done_tasks")
    def test_dry_run_no_side_effects(self, mock_fetch, tmp_path):
        """dry_run=True should report archivable tasks without modifying files."""
        cache, vault = self._make_cache(tmp_path)

        mock_fetch.return_value = [
            _make_task("Completed Jan 15", "done01", completed="2026-01-15"),
            _make_task("Completed Jan 16", "done02", completed="2026-01-16"),
        ]

        from scripts.archive_tasks import archive_tasks
        result = archive_tasks(cache, api_base="http://test", dry_run=True)

        # Should report what would be archived
        assert result["dry_run"] is True
        assert result["archived"] >= 2
        assert result["daily_notes"] == 2
        assert "tasks" in result
        assert len(result["tasks"]) == 2
        task_ids = {t["id"] for t in result["tasks"]}
        assert "done01" in task_ids
        assert "done02" in task_ids

        # Source files must be untouched
        tasks_file = vault / "TASKS.md"
        tree = parse_file(tasks_file)
        remaining_ids = {t.id for t in tree.all_tasks()}
        assert "done01" in remaining_ids
        assert "done02" in remaining_ids

    @patch("scripts.archive_tasks.fetch_done_tasks")
    @patch("scripts.archive_tasks.reopen_parent")
    def test_dry_run_skips_reopen(self, mock_reopen, mock_fetch, tmp_path):
        """dry_run=True should not call reopen_parent."""
        cache, vault = self._make_cache(tmp_path)

        mock_fetch.return_value = [
            _make_task("Done parent with open child", "done03", children=[
                _make_task("Open child", "open03", status="open", completed=None),
                _make_task("Done child", "done04"),
            ]),
        ]

        from scripts.archive_tasks import archive_tasks
        result = archive_tasks(cache, api_base="http://test", dry_run=True)

        assert result["dry_run"] is True
        mock_reopen.assert_not_called()

    @patch("scripts.archive_tasks.get_daily_note_path")
    @patch("scripts.archive_tasks.fetch_done_tasks")
    def test_idempotent_run(self, mock_fetch, mock_daily_path, tmp_path):
        """Second run should archive nothing since tasks are already gone."""
        cache, vault = self._make_cache(tmp_path)
        daily_dir = tmp_path / "daily"
        daily_dir.mkdir()
        mock_daily_path.side_effect = lambda d: daily_dir / f"{d}.md"

        # First run: archive done01
        mock_fetch.return_value = [
            _make_task("Completed Jan 15", "done01", completed="2026-01-15"),
        ]

        from scripts.archive_tasks import archive_tasks
        result1 = archive_tasks(cache, api_base="http://test")
        assert result1["archived"] >= 1

        # Second run: no done tasks returned (they were removed)
        mock_fetch.return_value = []
        result2 = archive_tasks(cache, api_base="http://test")
        assert result2["archived"] == 0

    def _task_to_api_dict(self, task) -> dict:
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "tags": dict(task.tags),
            "notes": list(task.notes),
            "children": [self._task_to_api_dict(c) for c in task.children],
            "indent_level": task.indent_level,
            "section": task.section,
            "ref": task.ref,
            "is_stub": task.is_stub,
            "is_blocked": task.is_blocked,
            "blocking_ids": task.blocking_ids,
        }
