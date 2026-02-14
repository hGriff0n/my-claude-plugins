#!/usr/bin/env python3
"""
Unit tests for the refactored parser (scripts/new/).
"""

import sys
from pathlib import Path
import tempfile

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "new"))

import pytest
from parser import (
    parse_task_line,
    parse_content,
    parse_file,
    write_file,
    parse_checkbox_state,
    calculate_indent_level,
    split_tags,
)
from models import (
    Task,
    TaskTree,
    format_task,
    format_checkbox_state,
    format_tree,
    format_tag,
    format_tags,
)


def test_calculate_indent_level():
    """Test indent level calculation."""
    # No indent
    assert calculate_indent_level('') == 0

    # Tab indents
    assert calculate_indent_level('\t') == 1
    assert calculate_indent_level('\t\t') == 2
    assert calculate_indent_level('\t\t\t') == 3

    # Space indents (4 spaces = 1 level)
    assert calculate_indent_level('    ') == 1
    assert calculate_indent_level('        ') == 2
    assert calculate_indent_level('            ') == 3

    # Mixed (tabs + spaces)
    assert calculate_indent_level('\t    ') == 2
    assert calculate_indent_level('    \t') == 2


def test_parse_checkbox_state():
    """Test checkbox state parsing."""
    assert parse_checkbox_state(' ') == 'open'
    assert parse_checkbox_state('x') == 'done'
    assert parse_checkbox_state('X') == 'done'
    assert parse_checkbox_state('/') == 'in-progress'


def test_format_checkbox_state():
    """Test checkbox state formatting."""
    assert format_checkbox_state('open') == '[ ]'
    assert format_checkbox_state('done') == '[x]'
    assert format_checkbox_state('in-progress') == '[/]'


def test_parse_task_line_basic():
    """Test basic task line parsing."""
    line = "- [ ] Simple task"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Simple task"
    assert result['status'] == 'open'
    assert result['indent_level'] == 0


def test_parse_task_line_with_emoji_tags():
    """Test task line with emoji tags."""
    line = "- [ ] Task title 🆔 abc123 📅 2026-02-15"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Task title"
    assert result['tags']['id'] == 'abc123'
    assert result['tags']['due'] == '2026-02-15'


def test_parse_task_line_with_hashtag_tags():
    """Test task line with hashtag tags."""
    line = "- [ ] Task title #estimate:4h #stub"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Task title"
    assert result['tags']['estimate'] == '4h'
    assert result['tags']['stub'] == ''


def test_parse_task_line_mixed_tags():
    """Test task line with mixed emoji and hashtag tags."""
    line = "- [x] Complete task 🆔 xyz789 #estimate:2h ✅ 2026-02-10"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Complete task"
    assert result['status'] == 'done'
    assert result['tags']['id'] == 'xyz789'
    assert result['tags']['estimate'] == '2h'
    assert result['tags']['completed'] == '2026-02-10'


def test_parse_task_line_indented_spaces():
    """Test indented task with spaces (subtask)."""
    line = "    - [ ] Subtask"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Subtask"
    assert result['indent_level'] == 1


def test_parse_task_line_indented_tabs():
    """Test indented task with tabs (subtask)."""
    line = "\t- [ ] Subtask"
    result = parse_task_line(line)

    assert result is not None
    assert result['title'] == "Subtask"
    assert result['indent_level'] == 1


def test_parse_content_simple():
    """Test parsing simple content without frontmatter."""
    content = """
### Open

- [ ] Task 1 🆔 abc123
- [ ] Task 2 🆔 def456

### Closed

- [x] Task 3 🆔 ghi789
"""

    frontmatter, tree = parse_content(content)

    assert len(frontmatter) == 0
    assert len(tree.tasks) == 3
    assert tree.tasks[0].title == "Task 1"
    assert tree.tasks[0].id == "abc123"
    assert tree.tasks[0].status == "open"
    assert tree.tasks[0].section == "Open"
    assert tree.tasks[2].status == "done"
    assert tree.tasks[2].section == "Closed"


def test_parse_content_with_frontmatter():
    """Test parsing content with YAML frontmatter."""
    content = """---
title: My Tasks
version: 1.0
---

### Open

- [ ] Task 1 🆔 abc123
"""

    frontmatter, tree = parse_content(content)

    assert len(frontmatter) == 4
    assert frontmatter[0] == '---'
    assert 'title: My Tasks' in frontmatter
    assert frontmatter[-1] == '---'

    assert len(tree.tasks) == 1
    assert tree.tasks[0].title == "Task 1"


def test_parse_content_with_children():
    """Test parsing tasks with subtasks."""
    content = """
- [ ] Parent task 🆔 parent1
    - [ ] Child 1 🆔 child1
    - [ ] Child 2 🆔 child2
        - [ ] Grandchild 🆔 grand1
"""

    frontmatter, tree = parse_content(content)

    assert len(tree.tasks) == 1
    assert tree.tasks[0].title == "Parent task"
    assert len(tree.tasks[0].children) == 2
    assert tree.tasks[0].children[0].title == "Child 1"
    assert len(tree.tasks[0].children[1].children) == 1
    assert tree.tasks[0].children[1].children[0].title == "Grandchild"


def test_parse_content_with_notes():
    """Test parsing tasks with freeform notes."""
    content = """
- [ ] Task with notes 🆔 abc123
    - Note line 1
    - Note line 2
    - [ ] Subtask 🆔 def456
"""

    frontmatter, tree = parse_content(content)

    assert len(tree.tasks) == 1
    assert tree.tasks[0].title == "Task with notes"
    assert len(tree.tasks[0].notes) == 2
    assert tree.tasks[0].notes[0] == "Note line 1"
    assert len(tree.tasks[0].children) == 1


def test_parse_content_tracks_sections():
    """Test that task sections are tracked."""
    content = """
### Open

- [ ] Task 1 🆔 t1

### Closed

- [x] Task 2 🆔 t2

#### Archive

- [x] Task 3 🆔 t3
"""

    frontmatter, tree = parse_content(content)

    # Verify tasks are assigned to correct sections
    assert tree.tasks[0].section == "Open"
    assert tree.tasks[1].section == "Closed"
    assert tree.tasks[2].section == "Archive"


def test_task_is_leaf():
    """Test Task.is_leaf property."""
    parent = Task(title="Parent", id="p1")
    child = Task(title="Child", id="c1")
    parent.children.append(child)

    assert child.is_leaf
    assert not parent.is_leaf


def test_task_is_stub():
    """Test Task.is_stub property."""
    task_stub = Task(title="Stub task", id="s1", tags={'stub': ''})
    task_normal = Task(title="Normal task", id="n1")

    assert task_stub.is_stub
    assert not task_normal.is_stub


def test_task_is_blocked():
    """Test Task.is_blocked property."""
    task_blocked = Task(title="Blocked", id="b1", tags={'b': 'xyz123'})
    task_free = Task(title="Free", id="f1")

    assert task_blocked.is_blocked
    assert not task_free.is_blocked


def test_task_blocking_ids():
    """Test Task.blocking_ids property."""
    task = Task(title="Multi-blocked", id="m1", tags={'b': 'abc,def,ghi'})

    assert task.blocking_ids == ['abc', 'def', 'ghi']


def test_tree_all_tasks():
    """Test TaskTree.all_tasks() flattening."""
    content = """
- [ ] Task 1 🆔 t1
   - [ ] Task 1.1 🆔 t1_1
   - [ ] Task 1.2 🆔 t1_2
- [ ] Task 2 🆔 t2
"""

    _, tree = parse_content(content)
    all_tasks = tree.all_tasks()

    assert len(all_tasks) == 4
    assert all_tasks[0].id == 't1'
    assert all_tasks[1].id == 't1_1'
    assert all_tasks[2].id == 't1_2'
    assert all_tasks[3].id == 't2'


def test_tree_find_by_id():
    """Test TaskTree.find_by_id()."""
    content = """
- [ ] Task 1 🆔 abc123
   - [ ] Task 1.1 🆔 def456
"""

    _, tree = parse_content(content)

    found = tree.find_by_id('def456')
    assert found is not None
    assert found.title == "Task 1.1"

    not_found = tree.find_by_id('xyz999')
    assert not_found is None


def test_tree_find_by_title():
    """Test TaskTree.find_by_title()."""
    content = """
- [ ] Implement authentication 🆔 t1
- [ ] Add user profile 🆔 t2
- [ ] Write auth tests 🆔 t3
"""

    _, tree = parse_content(content)

    matches = tree.find_by_title('auth')
    assert len(matches) == 2
    assert matches[0].title == "Implement authentication"
    assert matches[1].title == "Write auth tests"


def test_format_task_simple():
    """Test formatting a simple task."""
    task = Task(
        title="Simple task",
        id="abc123",
        status="open",
        tags={'id': 'abc123', 'due': '2026-02-15'}
    )

    formatted = format_task(task)
    assert "- [ ] Simple task" in formatted
    assert "🆔 abc123" in formatted
    assert "📅 2026-02-15" in formatted


def test_format_task_with_children():
    """Test formatting a task with children."""
    parent = Task(title="Parent", id="p1", tags={'id': 'p1'})
    child = Task(title="Child", id="c1", tags={'id': 'c1'})
    parent.children.append(child)

    formatted = format_task(parent)

    assert "- [ ] Parent 🆔 p1" in formatted
    assert "    - [ ] Child 🆔 c1" in formatted


def test_format_tree_simple():
    """Test that format_tree formats tasks."""
    content = """
- [ ] Task 1 🆔 t1
- [ ] Task 2 🆔 t2
- [x] Task 3 🆔 t3
"""

    _, tree = parse_content(content)
    formatted = format_tree(tree)

    # Verify all tasks are present
    assert "Task 1" in formatted
    assert "Task 2" in formatted
    assert "Task 3" in formatted
    assert "🆔 t1" in formatted
    assert "🆔 t3" in formatted


def test_parse_file_and_write_file_roundtrip():
    """Test that parse_file and write_file can roundtrip."""
    original_content = """---
title: Test Tasks
---

### Open

- [ ] Task 1 🆔 abc123
    - [ ] Subtask 🆔 def456

### Closed

- [x] Done task 🆔 ghi789
"""

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(original_content)
        temp_path = Path(f.name)

    try:
        # Parse the file
        frontmatter, tree = parse_file(temp_path)

        # Verify parsing
        assert len(frontmatter) == 3
        assert 'title: Test Tasks' in frontmatter
        assert len(tree.tasks) == 2  # Parent and done task (subtask is child)

        # Modify a task
        task = tree.find_by_id('abc123')
        assert task is not None
        task.status = 'in-progress'

        # Write back
        write_file(temp_path, frontmatter, tree)

        # Re-parse
        frontmatter2, tree2 = parse_file(temp_path)

        # Verify the modification persisted
        task2 = tree2.find_by_id('abc123')
        assert task2 is not None
        assert task2.status == 'in-progress'

        # Verify frontmatter preserved
        assert frontmatter == frontmatter2

    finally:
        # Clean up
        temp_path.unlink()


def test_empty_file():
    """Test parsing an empty file."""
    content = ""
    frontmatter, tree = parse_content(content)

    assert len(frontmatter) == 0
    assert len(tree.tasks) == 0


def test_frontmatter_only():
    """Test parsing a file with only frontmatter."""
    content = """---
title: Empty Tasks
---
"""
    frontmatter, tree = parse_content(content)

    assert len(frontmatter) == 3
    assert len(tree.tasks) == 0


def test_frontmatter_with_leading_whitespace():
    """Test parsing frontmatter that's not on the first line."""
    content = """

---
title: My Tasks
---

### Open

- [ ] Task 1 🆔 t1
"""
    frontmatter, tree = parse_content(content)

    assert len(frontmatter) == 3
    assert 'title: My Tasks' in frontmatter
    assert len(tree.tasks) == 1
    assert tree.tasks[0].title == "Task 1"


def test_tasks_without_sections():
    """Test parsing tasks without section headings."""
    content = """
- [ ] Task 1 🆔 t1
- [ ] Task 2 🆔 t2
"""
    frontmatter, tree = parse_content(content)

    assert len(tree.tasks) == 2
    assert tree.tasks[0].section is None
    assert tree.tasks[1].section is None


def test_task_str_method():
    """Test that Task.__str__ works correctly."""
    task = Task(
        title="Test task",
        id="t1",
        status="open",
        tags={'id': 't1', 'due': '2026-02-15'}
    )

    task_str = str(task)
    assert "- [ ] Test task" in task_str
    assert "🆔 t1" in task_str
    assert "📅 2026-02-15" in task_str


def test_split_tags_basic():
    """Test split_tags with various tag formats."""
    # Emoji tags
    title, tags = split_tags("Task title 🆔 abc123 📅 2026-02-15")
    assert title == "Task title"
    assert tags['id'] == 'abc123'
    assert tags['due'] == '2026-02-15'

    # Hashtag tags
    title, tags = split_tags("Task title #estimate:4h #stub")
    assert title == "Task title"
    assert tags['estimate'] == '4h'
    assert tags['stub'] == ''

    # Mixed tags
    title, tags = split_tags("Task title 🆔 xyz #estimate:2h")
    assert title == "Task title"
    assert tags['id'] == 'xyz'
    assert tags['estimate'] == '2h'

    # No tags
    title, tags = split_tags("Task title")
    assert title == "Task title"
    assert len(tags) == 0


def test_format_tag():
    """Test format_tag for different tag types."""
    # Emoji tag
    assert format_tag('id', 'abc123') == '🆔 abc123'
    assert format_tag('due', '2026-02-15') == '📅 2026-02-15'

    # Hashtag tag with value
    assert format_tag('estimate', '4h') == '#estimate:4h'

    # Hashtag tag without value
    assert format_tag('stub', '') == '#stub'


def test_format_tags_priority():
    """Test that format_tags respects priority order."""
    tags = {
        'stub': '',
        'estimate': '2h',
        'id': 'abc123',
        'due': '2026-02-15',
    }

    formatted = format_tags(tags)

    # id should come before due, which should come before estimate, which should come before stub
    id_pos = formatted.index('🆔')
    due_pos = formatted.index('📅')
    estimate_pos = formatted.index('#estimate')
    stub_pos = formatted.index('#stub')

    assert id_pos < due_pos < estimate_pos < stub_pos


def test_task_add_blocker():
    """Test Task.add_blocker() method."""
    task = Task(title="Task", id="t1")

    # Add first blocker
    task.add_blocker("blocker1")
    assert task.is_blocked
    assert task.blocking_ids == ["blocker1"]
    assert task.tags['b'] == "blocker1"

    # Add second blocker
    task.add_blocker("blocker2")
    assert task.blocking_ids == ["blocker1", "blocker2"]
    assert task.tags['b'] == "blocker1,blocker2"

    # Adding duplicate should not change anything
    task.add_blocker("blocker1")
    assert task.blocking_ids == ["blocker1", "blocker2"]


def test_task_remove_blocker():
    """Test Task.remove_blocker() method."""
    task = Task(
        title="Task",
        id="t1",
        tags={'b': 'blocker1,blocker2,blocker3'}
    )

    # Remove middle blocker
    task.remove_blocker("blocker2")
    assert task.blocking_ids == ["blocker1", "blocker3"]
    assert task.tags['b'] == "blocker1,blocker3"

    # Remove first blocker
    task.remove_blocker("blocker1")
    assert task.blocking_ids == ["blocker3"]
    assert task.tags['b'] == "blocker3"

    # Remove last blocker (should remove tag entirely)
    task.remove_blocker("blocker3")
    assert not task.is_blocked
    assert task.blocking_ids == []
    assert 'b' not in task.tags
    assert 'blocked' not in task.tags

    # Removing non-existent blocker should not error
    task.remove_blocker("nonexistent")
    assert task.blocking_ids == []


def test_task_blocker_roundtrip():
    """Test that adding/removing blockers works with formatting."""
    task = Task(title="Task", id="t1", tags={'id': 't1'})

    # Add blocker and format
    task.add_blocker("blocker1")
    formatted = format_task(task)
    assert "⛔ blocker1" in formatted

    # Parse back and verify
    _, tree = parse_content(formatted)
    parsed_task = tree.tasks[0]
    assert parsed_task.is_blocked
    assert parsed_task.blocking_ids == ["blocker1"]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
