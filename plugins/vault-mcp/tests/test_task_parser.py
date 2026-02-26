"""
Tests for parsers/task_parser.py.

Covers:
- parse_content: sections, tasks, tags, nesting, notes
- split_tags: emoji tags, hashtag tags, value-less tags
- Frontmatter extraction
- Round-trip: parse → write_file → parse → verify identical structure
"""

import sys
from pathlib import Path

# Add src to path so imports work without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import tempfile

from parsers.task_parser import parse_content, parse_file, split_tags, write_file


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# split_tags
# ---------------------------------------------------------------------------

class TestSplitTags:
    def test_no_tags(self):
        title, tags = split_tags("Just a task title")
        assert title == "Just a task title"
        assert tags == {}

    def test_emoji_id_tag(self):
        title, tags = split_tags("My task 🆔 abc123")
        assert title == "My task"
        assert tags["id"] == "abc123"

    def test_emoji_due_tag(self):
        title, tags = split_tags("Fix bug 📅 2026-02-15")
        assert title == "Fix bug"
        assert tags["due"] == "2026-02-15"

    def test_emoji_created_tag(self):
        title, tags = split_tags("New task ➕ 2026-01-01")
        assert title == "New task"
        assert tags["created"] == "2026-01-01"

    def test_emoji_scheduled_tag(self):
        title, tags = split_tags("Review PR ⏳ 2026-02-20")
        assert title == "Review PR"
        assert tags["scheduled"] == "2026-02-20"

    def test_emoji_completed_tag(self):
        title, tags = split_tags("Done task ✅ 2026-01-15")
        assert title == "Done task"
        assert tags["completed"] == "2026-01-15"

    def test_emoji_blocked_tag(self):
        title, tags = split_tags("Blocked task ⛔ abc123")
        assert title == "Blocked task"
        assert tags["b"] == "abc123"

    def test_hashtag_with_value(self):
        title, tags = split_tags("Work item #estimate:2h")
        assert title == "Work item"
        assert tags["estimate"] == "2h"

    def test_hashtag_without_value(self):
        title, tags = split_tags("Placeholder task #stub")
        assert title == "Placeholder task"
        assert tags["stub"] == ""

    def test_multiple_tags(self):
        title, tags = split_tags("Complex task 🆔 x1y2z3 📅 2026-03-01 #estimate:4h #stub")
        assert title == "Complex task"
        assert tags["id"] == "x1y2z3"
        assert tags["due"] == "2026-03-01"
        assert tags["estimate"] == "4h"
        assert tags["stub"] == ""

    def test_title_preserved_with_parens(self):
        title, tags = split_tags("Fix (something) important 🆔 abc123")
        assert "Fix (something) important" in title

    def test_wikilink_hash_not_parsed_as_tag(self):
        title, tags = split_tags("See [[Foo#Bar]] for details 🆔 abc123")
        assert "[[Foo#Bar]]" in title
        assert "Bar" not in tags
        assert tags["id"] == "abc123"

    def test_wikilink_section_and_block(self):
        title, tags = split_tags("Ref [[Foo#Bar^Baz]] here #stub")
        assert "[[Foo#Bar^Baz]]" in title
        assert "Bar" not in tags
        assert "stub" in tags

    def test_wikilink_with_alias(self):
        title, tags = split_tags("Check [[Note#Section|display text]] 🆔 def456")
        assert "[[Note#Section|display text]]" in title
        assert "Section" not in tags
        assert tags["id"] == "def456"

    def test_plain_wikilink_no_hash(self):
        title, tags = split_tags("See [[SomeNote]] for info #estimate:2h")
        assert "[[SomeNote]]" in title
        assert tags["estimate"] == "2h"

    def test_multiple_wikilinks(self):
        title, tags = split_tags("Link [[A#B]] and [[C#D^E]] 📅 2026-03-01 🆔 abc123")
        assert "[[A#B]]" in title
        assert "[[C#D^E]]" in title
        assert "B" not in tags
        assert "D" not in tags
        assert tags["due"] == "2026-03-01"
        assert tags["id"] == "abc123"
        assert tags["id"] == "abc123"


# ---------------------------------------------------------------------------
# parse_content: sections
# ---------------------------------------------------------------------------

class TestParseContentSections:
    def test_single_section(self):
        content = "### Open\n\n- [ ] A task 🆔 aaaaaa\n"
        tree = parse_content(content)
        assert len(tree.sections) == 1
        assert tree.sections[0].heading == "Open"
        assert tree.sections[0].level == 3

    def test_multiple_sections(self):
        content = (
            "### Open\n\n- [ ] Task A 🆔 aaa111\n\n"
            "### Done\n\n- [x] Task B 🆔 bbb222\n"
        )
        tree = parse_content(content)
        assert len(tree.sections) == 2
        assert tree.sections[0].heading == "Open"
        assert tree.sections[1].heading == "Done"

    def test_section_levels_preserved(self):
        content = "## Projects\n\n- [ ] Task 🆔 cc3333\n\n#### Sub\n\n- [ ] Subtask 🆔 dd4444\n"
        tree = parse_content(content)
        assert tree.sections[0].level == 2
        assert tree.sections[1].level == 4

    def test_empty_sections_allowed(self):
        content = "### Open\n\n### Done\n\n- [x] A task 🆔 ee5555\n"
        tree = parse_content(content)
        assert len(tree.sections) == 2
        assert len(tree.sections[0].tasks) == 0
        assert len(tree.sections[1].tasks) == 1


# ---------------------------------------------------------------------------
# parse_content: tasks
# ---------------------------------------------------------------------------

class TestParseContentTasks:
    def test_open_task(self):
        tree = parse_content("### Open\n\n- [ ] Open task 🆔 ff6666\n")
        task = tree.sections[0].tasks[0]
        assert task.status == "open"
        assert task.title == "Open task"

    def test_in_progress_task(self):
        tree = parse_content("### In Progress\n\n- [/] In progress 🆔 gg7777\n")
        task = tree.sections[0].tasks[0]
        assert task.status == "in-progress"

    def test_done_task(self):
        tree = parse_content("### Done\n\n- [x] Completed 🆔 hh8888\n")
        task = tree.sections[0].tasks[0]
        assert task.status == "done"

    def test_task_id_set(self):
        tree = parse_content("### Open\n\n- [ ] Task 🆔 abc999\n")
        assert tree.sections[0].tasks[0].id == "abc999"

    def test_task_section_set(self):
        tree = parse_content("### My Section\n\n- [ ] Task 🆔 sec001\n")
        assert tree.sections[0].tasks[0].section == "My Section"

    def test_task_section_level_set(self):
        tree = parse_content("#### Deep\n\n- [ ] Task 🆔 lvl001\n")
        assert tree.sections[0].tasks[0].section_level == 4

    def test_task_indent_level(self):
        content = "### Open\n\n- [ ] Parent 🆔 par001\n    - [ ] Child 🆔 chi001\n"
        tree = parse_content(content)
        parent = tree.sections[0].tasks[0]
        child = parent.children[0]
        assert parent.indent_level == 0
        assert child.indent_level == 1

    def test_nested_tasks(self):
        content = "### Open\n\n- [ ] Parent 🆔 nest01\n    - [ ] Child 🆔 nest02\n        - [ ] Grandchild 🆔 nest03\n"
        tree = parse_content(content)
        parent = tree.sections[0].tasks[0]
        assert len(parent.children) == 1
        child = parent.children[0]
        assert len(child.children) == 1
        assert child.children[0].id == "nest03"

    def test_multiple_root_tasks(self):
        content = "### Open\n\n- [ ] Task A 🆔 ta0001\n- [ ] Task B 🆔 tb0001\n"
        tree = parse_content(content)
        assert len(tree.sections[0].tasks) == 2

    def test_is_stub(self):
        tree = parse_content("### Open\n\n- [ ] Stub task 🆔 stub01 #stub\n")
        assert tree.sections[0].tasks[0].is_stub is True

    def test_is_blocked(self):
        tree = parse_content("### Open\n\n- [ ] Blocked 🆔 blk001 ⛔ abc123\n")
        task = tree.sections[0].tasks[0]
        assert task.is_blocked is True
        assert "abc123" in task.blocking_ids

    def test_is_atomic_leaf(self):
        tree = parse_content("### Open\n\n- [ ] Leaf 🆔 leaf01\n")
        assert tree.sections[0].tasks[0].is_atomic is True

    def test_is_atomic_parent(self):
        content = "### Open\n\n- [ ] Parent 🆔 par002\n    - [ ] Child 🆔 chi002\n"
        tree = parse_content(content)
        assert tree.sections[0].tasks[0].is_atomic is False


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_no_frontmatter(self):
        tree = parse_content("### Open\n\n- [ ] Task 🆔 fm0001\n")
        assert tree.frontmatter_lines == []

    def test_frontmatter_preserved(self):
        content = "---\ntags: [test]\n---\n\n### Open\n\n- [ ] Task 🆔 fm0002\n"
        tree = parse_content(content)
        assert len(tree.frontmatter_lines) == 3
        assert tree.frontmatter_lines[0].strip() == "---"
        assert "tags" in tree.frontmatter_lines[1]
        assert tree.frontmatter_lines[2].strip() == "---"

    def test_frontmatter_body_parsed(self):
        content = "---\ntags: [test]\n---\n\n### Open\n\n- [ ] Task 🆔 fm0003\n"
        tree = parse_content(content)
        assert len(tree.sections) == 1
        assert len(tree.sections[0].tasks) == 1


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

class TestNotes:
    def test_note_attached_to_task(self):
        content = "### Open\n\n- [ ] Task with note 🆔 note01\n    - This is a note\n"
        tree = parse_content(content)
        task = tree.sections[0].tasks[0]
        assert len(task.notes) == 1
        assert "This is a note" in task.notes[0]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_round_trip_sample_file(self):
        """Parse sample_tasks.md, write to temp file, re-parse, verify structure."""
        sample = FIXTURES_DIR / "sample_tasks.md"
        tree1 = parse_file(sample)

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = Path(f.name)

        try:
            write_file(tmp_path, tree1)
            tree2 = parse_file(tmp_path)

            # Same number of sections
            assert len(tree2.sections) == len(tree1.sections)

            # Same section headings
            headings1 = [s.heading for s in tree1.sections]
            headings2 = [s.heading for s in tree2.sections]
            assert headings1 == headings2

            # Same task IDs (tasks with IDs)
            ids1 = {t.id for t in tree1.all_tasks() if t.id}
            ids2 = {t.id for t in tree2.all_tasks() if t.id}
            assert ids1 == ids2

            # Same task titles
            titles1 = {t.title for t in tree1.all_tasks()}
            titles2 = {t.title for t in tree2.all_tasks()}
            assert titles1 == titles2

            # Frontmatter preserved
            assert len(tree2.frontmatter_lines) == len(tree1.frontmatter_lines)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_round_trip_preserves_status(self):
        content = "### Done\n\n- [x] Finished 🆔 rt0001 ✅ 2026-01-01\n"
        tree1 = parse_content(content, Path("test.md"))

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = Path(f.name)

        try:
            write_file(tmp_path, tree1)
            tree2 = parse_file(tmp_path)
            assert tree2.sections[0].tasks[0].status == "done"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_round_trip_nested_tasks(self):
        content = "### Open\n\n- [ ] Parent 🆔 rt0002 #stub\n    - [ ] Child 🆔 rt0003\n"
        tree1 = parse_content(content, Path("test.md"))

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = Path(f.name)

        try:
            write_file(tmp_path, tree1)
            tree2 = parse_file(tmp_path)
            parent = tree2.sections[0].tasks[0]
            assert parent.id == "rt0002"
            assert len(parent.children) == 1
            assert parent.children[0].id == "rt0003"
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# parse_file with fixtures
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_parse_sample_tasks_sections(self):
        tree = parse_file(FIXTURES_DIR / "sample_tasks.md")
        headings = [s.heading for s in tree.sections]
        assert "Open" in headings
        assert "In Progress" in headings
        assert "Done" in headings

    def test_parse_sample_tasks_ids(self):
        tree = parse_file(FIXTURES_DIR / "sample_tasks.md")
        all_ids = {t.id for t in tree.all_tasks() if t.id}
        # Tasks defined in the fixture
        assert "a1b2c3" in all_ids
        assert "d4e5f6" in all_ids
        assert "p6q7r8" in all_ids

    def test_parse_sample_tasks_nested(self):
        tree = parse_file(FIXTURES_DIR / "sample_tasks.md")
        # "Write unit tests" (d4e5f6) has two children
        d4e5f6 = tree.find_by_id("d4e5f6")
        assert d4e5f6 is not None
        assert len(d4e5f6.children) == 2

    def test_parse_sample_tasks_frontmatter(self):
        tree = parse_file(FIXTURES_DIR / "sample_tasks.md")
        assert len(tree.frontmatter_lines) > 0
