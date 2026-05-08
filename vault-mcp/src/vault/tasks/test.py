"""Tests for vault/tasks/parser.py."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from schemas.tasks import (  # noqa: E402
    Dependencies,
    Task,
    TaskStatus,
    TaskType,
)
from schemas.time import TimeBlock  # noqa: E402
from vault.tasks.parser import (  # noqa: E402
    ArchiveTask,
    CreateTask,
    ROOT_TASKFILE,
    TaskParser,
    UpdateDependencies,
    UpdateMetadata,
    UpdateStatus,
    UpdateText,
    _indent_level,
    _skip_frontmatter,
    _split_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "efforts").mkdir()
    return tmp_path


def _stack(root: Path) -> TaskParser:
    """Build a fully-initialized TaskParser bound to a DB + debouncer."""
    from database import Database
    from schemas.efforts import Effort
    from vault.debounce import WriteDebouncer
    from vault.watcher import Watcher

    db = Database()
    db.register(Effort, system="efforts")
    db.register(Task, system="tasks")
    watcher = Watcher()
    debouncer = WriteDebouncer(watcher=watcher, wal_path=root / ".wal")
    db.attach_debouncer(debouncer)
    parser = TaskParser(root)
    parser.initialize(db, watcher, debouncer)
    return parser


def _apply(parser: TaskParser, task: Task, op) -> None:
    """Run an Update op end-to-end (DB mutation → file projection)."""
    parser.update(task, op)
    parser._debouncer.flush()


def _write_root_taskfile(root: Path, content: str) -> Path:
    path = root / ROOT_TASKFILE
    path.write_text(content, encoding="utf-8")
    return path


def _make_effort(root: Path, name: str, *, backlog: bool = False) -> Path:
    parent = root / "efforts" / ("__backlog" if backlog else "")
    folder = parent / name if backlog else root / "efforts" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "00 README.md").write_text("# " + name + "\n", encoding="utf-8")
    (folder / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    (folder / ROOT_TASKFILE).write_text("", encoding="utf-8")
    return folder


def _empty_time() -> TimeBlock:
    return TimeBlock()


def _empty_deps() -> Dependencies:
    return Dependencies(blocked=[], parent="", children=[])


def _placeholder_task(
    *,
    id: str = "",
    effort: str = "none",
    text: str = "Task",
    status: TaskStatus = TaskStatus.OPEN,
    tags: list[str] = None,
    deps: Dependencies = None,
    type: TaskType = TaskType.TASK,
    time_details: TimeBlock = None,
) -> Task:
    return Task(
        id=id,
        type=type,
        status=status,
        text=text,
        effort=effort,
        notes=[],
        tags=tags or [],
        dependencies=deps or _empty_deps(),
        time_details=time_details or _empty_time(),
    )


# ---------------------------------------------------------------------------
# _split_tags
# ---------------------------------------------------------------------------


class TestSplitTags:
    def test_no_tags(self):
        title, tags, dv = _split_tags("Just a task title")
        assert title == "Just a task title"
        assert tags == {}
        assert dv == set()

    def test_emoji_id_tag(self):
        title, tags, _ = _split_tags("My task 🆔 abc123")
        assert title == "My task"
        assert tags["id"] == "abc123"

    def test_emoji_due_tag(self):
        title, tags, _ = _split_tags("Fix bug 📅 2026-02-15")
        assert title == "Fix bug"
        assert tags["due"] == "2026-02-15"

    def test_emoji_scheduled_tag(self):
        _, tags, _ = _split_tags("Review ⏳ 2026-02-20")
        assert tags["scheduled"] == "2026-02-20"

    def test_emoji_created_tag(self):
        _, tags, _ = _split_tags("New ➕ 2026-01-01")
        assert tags["created"] == "2026-01-01"

    def test_emoji_blocked_tag(self):
        _, tags, _ = _split_tags("Blocked ⛔ abc123")
        assert tags["blocked"] == "abc123"

    def test_hashtag_with_value(self):
        title, tags, _ = _split_tags("Work item #estimate:2h")
        assert title == "Work item"
        assert tags["estimate"] == "2h"

    def test_hashtag_without_value(self):
        title, tags, _ = _split_tags("Stubby #stub")
        assert title == "Stubby"
        assert tags["stub"] == ""

    def test_dataview_paren(self):
        title, tags, dv = _split_tags("Task (estimate::4h)")
        assert title == "Task"
        assert tags["estimate"] == "4h"
        assert "estimate" in dv

    def test_dataview_bracket(self):
        title, tags, dv = _split_tags("Task [estimate:: 4h]")
        assert title == "Task"
        assert tags["estimate"] == "4h"
        assert "estimate" in dv

    def test_dataview_bracket_spaced(self):
        _, tags, dv = _split_tags("Task [ estimate :: 4h ]")
        assert tags["estimate"] == "4h"
        assert "estimate" in dv

    def test_unknown_emoji_after_known(self):
        # Unknown emoji is parsed once metadata starts via a known emoji.
        _, tags, _ = _split_tags("Task 🆔 abc123 🚴 [[412w]]")
        assert tags["🚴"] == "[[412w]]"

    def test_multiple_tags(self):
        title, tags, _ = _split_tags(
            "Complex 🆔 x1y2z3 📅 2026-03-01 #estimate:4h #stub"
        )
        assert title == "Complex"
        assert tags["id"] == "x1y2z3"
        assert tags["due"] == "2026-03-01"
        assert tags["estimate"] == "4h"
        assert tags["stub"] == ""

    def test_title_preserves_parens(self):
        title, _tags, _ = _split_tags("Fix (something) important 🆔 abc123")
        assert "Fix (something) important" in title

    def test_wikilink_hash_not_parsed_as_tag(self):
        title, tags, _ = _split_tags("See [[Foo#Bar]] for details 🆔 abc123")
        assert "[[Foo#Bar]]" in title
        assert "Bar" not in tags
        assert tags["id"] == "abc123"

    def test_wikilink_with_alias(self):
        title, tags, _ = _split_tags("Check [[Note#Section|alias]] 🆔 def456")
        assert "[[Note#Section|alias]]" in title
        assert "Section" not in tags
        assert tags["id"] == "def456"

    def test_dv_set_empty_for_emoji_only(self):
        _, _, dv = _split_tags("Task 🆔 abc123 📅 2026-01-01")
        assert dv == set()


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


class TestIndentLevel:
    def test_no_indent(self):
        assert _indent_level("") == 0

    def test_tab_indent(self):
        assert _indent_level("\t") == 1

    def test_four_space_indent(self):
        assert _indent_level("    ") == 1

    def test_double_indent(self):
        assert _indent_level("        ") == 2


class TestSkipFrontmatter:
    def test_no_frontmatter(self):
        assert _skip_frontmatter(["# Heading", "body"]) == 0

    def test_frontmatter_skipped(self):
        lines = ["---", "tags: [x]", "---", "", "# H"]
        assert _skip_frontmatter(lines) == 3

    def test_unterminated_frontmatter(self):
        lines = ["---", "tags: [x]", "# never closed"]
        assert _skip_frontmatter(lines) == 0


# scan() is no longer part of the parser surface; taskfile discovery now
# happens via the watcher's immediate-fire-on-register seed (see asyncfile.md).


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


class TestParse:
    def test_missing_file(self, tmp_path):
        assert TaskParser(_vault(tmp_path)).parse(tmp_path / "nope.md") == []

    def test_single_open_task(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "### Open\n\n- [ ] My task 🆔 abc123\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.id == "abc123"
        assert task.status == TaskStatus.OPEN
        assert task.text == "My task"
        assert task.effort == "none"
        assert task.type == TaskType.TASK

    def test_closed_task(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(root, "- [x] Done 🆔 done01\n")
        [task] = TaskParser(root).parse(path)
        assert task.status == TaskStatus.CLOSED

    def test_in_progress_task(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(root, "- [/] WIP 🆔 wip001\n")
        [task] = TaskParser(root).parse(path)
        assert task.status == TaskStatus.IN_PROGRESS

    def test_blocked_task(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "- [ ] Blocked 🆔 blk001 ⛔ other1\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.status == TaskStatus.BLOCKED
        assert task.dependencies.blocked == ["other1"]

    def test_blocked_multiple(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "- [ ] Blocked 🆔 blk002 ⛔ a1,b2\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.dependencies.blocked == ["a1", "b2"]

    def test_milestone_via_section(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "## Milestones\n\n- [ ] Ship 🆔 mil001\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.type == TaskType.MILESTONE

    def test_milestone_via_tag(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "- [ ] Ship 🆔 mil002 #milestone\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.type == TaskType.MILESTONE

    def test_milestone_via_heading(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root, "#### Release 🆔 mil003 📅 2026-05-01\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.id == "mil003"
        assert task.type == TaskType.MILESTONE
        assert task.text == "Release"
        assert task.time_details.due == date(2026, 5, 1)

    def test_milestone_heading_id_generated(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(root, "#### Auto id heading\n")
        [task] = TaskParser(root).parse(path)
        assert task.id
        assert task.type == TaskType.MILESTONE
        # Heading rewritten on disk with the new id.
        rewritten = path.read_text(encoding="utf-8")
        assert task.id in rewritten
        assert rewritten.startswith("#### Auto id heading")

    def test_milestone_heading_parents_top_level_tasks(self, tmp_path):
        root = _vault(tmp_path)
        content = (
            "#### Phase one 🆔 mil010\n"
            "\n"
            "- [ ] Top one 🆔 t00001\n"
            "    - [ ] Sub 🆔 sb0001\n"
            "- [ ] Top two 🆔 t00002\n"
        )
        path = _write_root_taskfile(root, content)
        tasks = {t.id: t for t in TaskParser(root).parse(path)}
        assert tasks["t00001"].dependencies.parent == "mil010"
        assert tasks["t00002"].dependencies.parent == "mil010"
        # Nested children still parent on the enclosing task, not the milestone.
        assert tasks["sb0001"].dependencies.parent == "t00001"
        assert sorted(tasks["mil010"].dependencies.children) == [
            "t00001", "t00002",
        ]

    def test_milestone_scope_ends_at_next_heading(self, tmp_path):
        root = _vault(tmp_path)
        content = (
            "#### Phase one 🆔 mil020\n"
            "- [ ] Inside 🆔 in0001\n"
            "## Other section\n"
            "- [ ] Outside 🆔 ou0001\n"
        )
        path = _write_root_taskfile(root, content)
        tasks = {t.id: t for t in TaskParser(root).parse(path)}
        assert tasks["in0001"].dependencies.parent == "mil020"
        assert tasks["ou0001"].dependencies.parent == ""

    def test_milestone_scope_ends_at_next_milestone(self, tmp_path):
        root = _vault(tmp_path)
        content = (
            "#### Phase one 🆔 mil030\n"
            "- [ ] First 🆔 fi0001\n"
            "#### Phase two 🆔 mil031\n"
            "- [ ] Second 🆔 sc0001\n"
        )
        path = _write_root_taskfile(root, content)
        tasks = {t.id: t for t in TaskParser(root).parse(path)}
        assert tasks["fi0001"].dependencies.parent == "mil030"
        assert tasks["sc0001"].dependencies.parent == "mil031"

    def test_parent_child(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root,
            "- [ ] Parent 🆔 par001\n    - [ ] Child 🆔 chi001\n",
        )
        tasks = TaskParser(root).parse(path)
        by_id = {t.id: t for t in tasks}
        assert by_id["par001"].dependencies.children == ["chi001"]
        assert by_id["chi001"].dependencies.parent == "par001"

    def test_grandchild_chain(self, tmp_path):
        root = _vault(tmp_path)
        content = (
            "- [ ] A 🆔 a00001\n"
            "    - [ ] B 🆔 b00001\n"
            "        - [ ] C 🆔 c00001\n"
        )
        path = _write_root_taskfile(root, content)
        tasks = {t.id: t for t in TaskParser(root).parse(path)}
        assert tasks["a00001"].dependencies.children == ["b00001"]
        assert tasks["b00001"].dependencies.parent == "a00001"
        assert tasks["b00001"].dependencies.children == ["c00001"]
        assert tasks["c00001"].dependencies.parent == "b00001"

    def test_notes_collected(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root,
            "- [ ] Task 🆔 nt0001\n    - first note\n    - second note\n",
        )
        [task] = TaskParser(root).parse(path)
        assert task.notes == ["first note", "second note"]

    def test_free_tags_excludes_reserved(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root,
            "- [ ] Task 🆔 ft0001 📅 2026-01-01 #stub #estimate:2h\n",
        )
        [task] = TaskParser(root).parse(path)
        # id, due, estimate are reserved; stub is free.
        assert "stub" in task.tags
        assert not any(t.startswith("id") for t in task.tags)
        assert not any(t.startswith("due") for t in task.tags)
        assert not any(t.startswith("estimate") for t in task.tags)

    def test_time_details_parsed(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(
            root,
            "- [ ] T 🆔 td0001 ➕ 2026-01-01 📅 2026-02-01 ⏳ 2026-01-15\n",
        )
        [task] = TaskParser(root).parse(path)
        assert task.time_details.created == date(2026, 1, 1)
        assert task.time_details.due == date(2026, 2, 1)
        assert task.time_details.scheduled == date(2026, 1, 15)

    def test_id_generated_when_missing(self, tmp_path):
        root = _vault(tmp_path)
        path = _write_root_taskfile(root, "- [ ] No id task\n")
        [task] = TaskParser(root).parse(path)
        assert task.id  # auto-generated
        # File should be rewritten with the new id
        rewritten = path.read_text(encoding="utf-8")
        assert task.id in rewritten

    def test_frontmatter_skipped(self, tmp_path):
        root = _vault(tmp_path)
        content = "---\ntags: [x]\n---\n\n- [ ] T 🆔 fm0001\n"
        path = _write_root_taskfile(root, content)
        [task] = TaskParser(root).parse(path)
        assert task.id == "fm0001"

    def test_effort_name_from_active(self, tmp_path):
        root = _vault(tmp_path)
        eff = _make_effort(root, "alpha")
        path = eff / ROOT_TASKFILE
        path.write_text("- [ ] T 🆔 aa0001\n", encoding="utf-8")
        [task] = TaskParser(root).parse(path)
        assert task.effort == "alpha"

    def test_effort_name_from_backlog(self, tmp_path):
        root = _vault(tmp_path)
        eff = _make_effort(root, "beta", backlog=True)
        path = eff / ROOT_TASKFILE
        path.write_text("- [ ] T 🆔 bb0001\n", encoding="utf-8")
        [task] = TaskParser(root).parse(path)
        assert task.effort == "beta"

    def test_wikilink_lines_ignored(self, tmp_path):
        root = _vault(tmp_path)
        # Lines starting with "- [[..." are not tasks.
        path = _write_root_taskfile(
            root, "- [[SomeNote]]\n- [ ] Real 🆔 wl0001\n"
        )
        [task] = TaskParser(root).parse(path)
        assert task.id == "wl0001"


# ---------------------------------------------------------------------------
# write: CreateTask
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_create_in_root(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "")
        parser = _stack(root)
        task = _placeholder_task(id="cr0001", text="Hello", effort="none")
        _apply(parser, task, CreateTask())
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "Hello" in text
        assert "cr0001" in text

    def test_create_assigns_id_when_missing(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "")
        parser = _stack(root)
        task = _placeholder_task(id="", text="Auto id")
        _apply(parser, task, CreateTask())
        assert task.id  # mutated
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert task.id in text

    def test_create_preserves_existing_lines(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] Existing 🆔 ex0001\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="cr0002", text="New"),
            CreateTask(),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "ex0001" in text
        assert "cr0002" in text

    def test_create_in_effort(self, tmp_path):
        root = _vault(tmp_path)
        _make_effort(root, "alpha")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="ef0001", effort="alpha", text="A task"),
            CreateTask(),
        )
        text = (root / "efforts" / "alpha" / ROOT_TASKFILE).read_text(
            encoding="utf-8"
        )
        assert "ef0001" in text

    def test_create_milestone_writes_heading(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "")
        parser = _stack(root)
        _apply(parser,
            _placeholder_task(
                id="ms0001", text="Ship", type=TaskType.MILESTONE
            ),
            CreateTask(),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "#### Ship" in text
        assert "ms0001" in text
        assert "- [ ] Ship" not in text

    # Strict effort-existence validation no longer applies: `update` is
    # DB-only and the debouncer's parent_file_resolver returns the canonical
    # path regardless of whether it currently exists.


# ---------------------------------------------------------------------------
# write: UpdateStatus / UpdateText
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_open_to_closed(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 us0001\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="us0001"),
            UpdateStatus(TaskStatus.CLOSED),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "- [x]" in text

    def test_open_to_in_progress(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 us0002\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="us0002"),
            UpdateStatus(TaskStatus.IN_PROGRESS),
        )
        assert "- [/]" in (root / ROOT_TASKFILE).read_text(encoding="utf-8")

    # Unknown-id validation no longer applies: `update` is DB-only and
    # upserts whatever it's given.


class TestUpdateText:
    def test_rewrites_title(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] Old title 🆔 ut0001\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="ut0001"),
            UpdateText("New title"),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "New title" in text
        assert "Old title" not in text
        assert "ut0001" in text  # tags preserved


# ---------------------------------------------------------------------------
# write: UpdateDependencies
# ---------------------------------------------------------------------------


class TestUpdateDependencies:
    def test_set_blocked(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 ud0001\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="ud0001"),
            UpdateDependencies(
                Dependencies(blocked=["aa1111"], parent="", children=[])
            ),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "aa1111" in text
        assert "⛔" in text

    def test_clear_blocked(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 ud0002 ⛔ aa1111\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="ud0002"),
            UpdateDependencies(_empty_deps()),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "⛔" not in text
        assert "aa1111" not in text


# ---------------------------------------------------------------------------
# write: UpdateMetadata
# ---------------------------------------------------------------------------


class TestUpdateMetadata:
    def test_replace_free_tags(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 um0001 #old\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="um0001"),
            UpdateMetadata(tags=["new"]),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "#new" in text
        assert "#old" not in text

    def test_clears_when_empty_list(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 um0002 #old\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="um0002"),
            UpdateMetadata(tags=[]),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "#old" not in text
        assert "um0002" in text  # id preserved

    def test_set_time_details(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 um0003\n")
        parser = _stack(root)
        td = TimeBlock(
            created=date(2026, 1, 1),
            due=date(2026, 2, 1),
        )
        _apply(parser, 
            _placeholder_task(id="um0003"),
            UpdateMetadata(time_details=td),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "2026-01-01" in text
        assert "2026-02-01" in text

    def test_clears_unset_time_details(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(
            root, "- [ ] T 🆔 um0004 📅 2026-02-01\n"
        )
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="um0004"),
            UpdateMetadata(time_details=_empty_time()),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "2026-02-01" not in text


# ---------------------------------------------------------------------------
# write: ArchiveTask
# ---------------------------------------------------------------------------


class TestArchiveTask:
    def test_removes_task_line(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(
            root,
            "- [ ] Keep 🆔 keep01\n- [x] Gone 🆔 arch01\n",
        )
        parser = _stack(root)
        _apply(parser, _placeholder_task(id="arch01"), ArchiveTask())
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "arch01" not in text
        assert "keep01" in text

    def test_removes_task_with_notes(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(
            root,
            "- [x] Gone 🆔 ap0001\n    - a note\n- [ ] Sib 🆔 sib001\n",
        )
        parser = _stack(root)
        _apply(parser, _placeholder_task(id="ap0001"), ArchiveTask())
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "ap0001" not in text
        assert "a note" not in text
        assert "sib001" in text

    def test_unknown_id_noop(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 keep02\n")
        parser = _stack(root)
        _apply(parser, _placeholder_task(id="ghost"), ArchiveTask())
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "keep02" in text


# ---------------------------------------------------------------------------
# write: dispatch errors
# ---------------------------------------------------------------------------


class TestWriteDispatch:
    def test_unknown_update_type_raises(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 dis001\n")
        parser = _stack(root)
        with pytest.raises(TypeError):
            _apply(parser, _placeholder_task(id="dis001"), object())


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_create_then_parse(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "")
        parser = _stack(root)
        original = _placeholder_task(
            id="rt0001",
            text="Round trip",
            tags=["stub"],
            time_details=TimeBlock(
                created=date(2026, 1, 1),
                due=date(2026, 2, 1),
            ),
        )
        _apply(parser, original, CreateTask())
        [parsed] = parser.parse(root / ROOT_TASKFILE)
        assert parsed.id == "rt0001"
        assert parsed.text == "Round trip"
        assert "stub" in parsed.tags
        assert parsed.time_details.created == date(2026, 1, 1)
        assert parsed.time_details.due == date(2026, 2, 1)

    def test_frontmatter_preserved_through_write(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(
            root,
            "---\ntags: [a, b]\nstatus: active\n---\n\n- [ ] T 🆔 fr0001\n",
        )
        parser = _stack(root)
        _apply(parser,
            _placeholder_task(id="fr0001"),
            UpdateText("Renamed"),
        )
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "tags: [a, b]" in text
        assert "status: active" in text
        assert "Renamed" in text

    def test_legacy_milestone_tag_migrates_to_heading(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(
            root, "- [ ] Ship 🆔 lg0001 #milestone\n"
        )
        parser = _stack(root)
        # Trigger a write by retitling the parsed milestone.
        [parsed] = parser.parse(root / ROOT_TASKFILE)
        assert parsed.type == TaskType.MILESTONE
        _apply(parser, parsed, UpdateText("Ship v2"))
        text = (root / ROOT_TASKFILE).read_text(encoding="utf-8")
        assert "#### Ship v2" in text
        assert "#milestone" not in text
        assert "- [ ] Ship" not in text

    def test_milestone_round_trip(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "")
        parser = _stack(root)
        _apply(parser,
            _placeholder_task(
                id="mr0001", text="Phase one", type=TaskType.MILESTONE,
            ),
            CreateTask(),
        )
        [parsed] = parser.parse(root / ROOT_TASKFILE)
        assert parsed.id == "mr0001"
        assert parsed.type == TaskType.MILESTONE
        assert parsed.text == "Phase one"

    def test_status_round_trip(self, tmp_path):
        root = _vault(tmp_path)
        _write_root_taskfile(root, "- [ ] T 🆔 rt0002\n")
        parser = _stack(root)
        _apply(parser, 
            _placeholder_task(id="rt0002"),
            UpdateStatus(TaskStatus.CLOSED),
        )
        [parsed] = parser.parse(root / ROOT_TASKFILE)
        assert parsed.status == TaskStatus.CLOSED
