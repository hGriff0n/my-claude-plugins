#!/usr/bin/env python3
"""
Parser for recursive markdown task trees.

Main API:
- parse_file(path) -> (frontmatter_lines, TaskTree)
- write_file(path, frontmatter_lines, tree) -> None

Features:
- Single-pass parsing of frontmatter, headings, and tasks
- Checkbox tasks with nested subtasks
- Tag extraction (#tag:value and emoji tags)
- Freeform notes (indented bullets without checkboxes)
- Parent/child relationships via indentation
- Section tracking via headings
"""

import re
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from models import Task, TaskTree, format_task, format_checkbox_state, TAG_TO_EMOJI

EMOJI_TO_TAG = {v:k for k, v in TAG_TO_EMOJI.items()}


def split_tags(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Split text into title and tags.

    Tags are always at the end of the string, so we find the earliest tag
    position and split there.

    Args:
        text: Text containing title and tags

    Returns:
        Tuple of (title, tags) where tags is a dict mapping tag names to values
    """
    tags = {}
    earliest_tag_pos = len(text)  # Start with end of string

    # Build combined pattern: (#tag:|emoji )<value> OR #tag
    emoji_pattern = '|'.join(re.escape(emoji) for emoji in EMOJI_TO_TAG.keys())
    # Groups: (1)=hashtag_with_value, (2)=emoji, (3)=value, (4)=hashtag_no_value
    combined_pattern = rf'(?:#([\w/-]+):|({emoji_pattern})\s+)(\S+)|#([\w/-]+)'

    # Single pass to extract all tags
    for match in re.finditer(combined_pattern, text):
        if match.group(1):  # Hashtag with value
            tag_name = match.group(1)
            tag_value = match.group(3)
            tags[tag_name] = tag_value
        elif match.group(2):  # Emoji with value
            emoji = match.group(2)
            tag_name = EMOJI_TO_TAG[emoji]
            tag_value = match.group(3)
            tags[tag_name] = tag_value
        elif match.group(4):  # Hashtag without value
            tag_name = match.group(4)
            tags[tag_name] = ""

        earliest_tag_pos = min(earliest_tag_pos, match.start())

    # Split at earliest tag position
    title = text[:earliest_tag_pos].strip()

    return title, tags


def calculate_indent_level(indent_str: str) -> int:
    """
    Calculate indentation level from indent string.

    Supports both tabs and spaces:
    - Tabs: 1 tab = 1 level
    - Spaces: 4 spaces = 1 level

    Args:
        indent_str: The indentation string (tabs and/or spaces)

    Returns:
        Indentation level (0 for no indent)
    """
    if not indent_str:
        return 0

    # Count spaces (4 spaces = 1 level)
    space_count = len(indent_str.replace('\t', '    '))
    space_levels = space_count // 4

    return space_levels


def parse_checkbox_state(checkbox: str) -> Literal["open", "in-progress", "done"]:
    """
    Parse checkbox state from markdown.

    Args:
        checkbox: Checkbox string (e.g., " ", "/", "x")

    Returns:
        Status: "open", "in-progress", or "done"
    """
    checkbox = checkbox.strip().lower()
    if checkbox == 'x':
        return "done"
    elif checkbox == '/':
        return "in-progress"
    else:
        return "open"


def parse_task_line(line: str) -> Optional[dict]:
    """
    Parse a single task line.

    Args:
        line: Markdown line

    Returns:
        Dict with task data or None if not a task line
    """
    # Pattern: "- [checkbox] Title with tags"
    match = re.match(r'^(\s*)- \[(.)\] (.+)$', line)
    if not match:
        return None

    indent = match.group(1)
    checkbox = match.group(2)
    content = match.group(3)

    # Split content into title and tags
    title, tags = split_tags(content)

    # Parse checkbox state
    status = parse_checkbox_state(checkbox)

    # Calculate indent level (supports tabs and 4-space indents)
    indent_level = calculate_indent_level(indent)

    return {
        'title': title,
        'status': status,
        'tags': tags,
        'indent_level': indent_level,
        'raw_line': line,
    }


def parse_heading_line(stripped: str) -> Optional[dict]:
    """
    Parse a markdown heading line (already stripped).

    Args:
        stripped: Stripped markdown line

    Returns:
        Dict with heading data or None if not a heading
    """
    if not stripped.startswith('#'):
        return None

    # Count the number of # characters
    level = 0
    for char in stripped:
        if char == '#':
            level += 1
        else:
            break

    # Extract heading text
    text = stripped[level:].strip()

    return {
        'level': level,
        'text': text,
    }


def parse_file(file_path: Path) -> Tuple[List[str], TaskTree]:
    """
    Parse a TASKS.md file into frontmatter and task tree.

    This function performs a single-pass parse of the file, extracting:
    - YAML frontmatter (if present)
    - Section headings
    - Task hierarchy with tags and notes

    Args:
        file_path: Path to the markdown file

    Returns:
        Tuple of (frontmatter_lines, TaskTree)
        - frontmatter_lines: List of frontmatter lines including delimiters
        - TaskTree: Parsed task tree with headings
    """
    content = file_path.read_text(encoding='utf-8')
    return parse_content(content, file_path)


def extract_frontmatter(lines_iter) -> Tuple[Optional[Tuple[int, str]], List[str], any]:
    """
    Extract the frontmatter from the fileline iterator.

    Args:
        lines_iter: Iterator of (line_num, line) tuples

    Returns:
        Tuple of (first_content_line, frontmatter_lines, remaining_iterator)
        - first_content_line: (line_num, line) tuple of first non-frontmatter line, or None if EOF
        - frontmatter_lines: List of frontmatter line strings (raw, not stripped)
        - remaining_iterator: The iterator to continue with
    """
    frontmatter_lines = []
    while True:
        item = next(lines_iter, None)
        if item is None:
            return None, [], lines_iter

        line_num, line = item
        stripped = line.strip()

        if not stripped:
            continue

        if stripped == '---':
            # If this is the second delimiter, then we are done with the frontmatter
            if frontmatter_lines:
                frontmatter_lines.append(line)
                # Return a fake whitespace line because of the behavior when there is
                # no frontmatter in the file.
                return (line_num, ''), frontmatter_lines, lines_iter

        # If we see something that's not whitespace and isn't frontmatter
        # (and we're not already parsing the frontmatter), we won't be seeing
        # any frontmatter in this file, so we can exit early
        elif not frontmatter_lines:
            return item, frontmatter_lines, lines_iter

        frontmatter_lines.append(line)


def parse_content(content: str, file_path: Optional[Path] = None) -> Tuple[List[str], TaskTree]:
    """
    Parse markdown content into frontmatter and task tree.

    Single-pass parsing of frontmatter, headings, and tasks.

    Args:
        content: Markdown file content
        file_path: Path to the file (optional, for TaskTree metadata)

    Returns:
        Tuple of (frontmatter_lines, TaskTree)
    """
    lines = content.split('\n')

    # Extract frontmatter (first non-whitespace content if it's ---)
    first_line, frontmatter_lines, lines_iter = extract_frontmatter(enumerate(lines))

    # first_line is only `None` if we reach the end of the file without extracting
    # a complete frontmatter header or seeing any non-whitespace characters
    # Return an empty tree for empty files
    if first_line is None:
        return frontmatter_lines, TaskTree(tasks=[], file_path=file_path)

    root_tasks = []
    task_stack: List[Task] = []  # Stack to track parent tasks by indent level
    current_task: Optional[Task] = None
    current_section: Optional[str] = None  # Track current section heading
    current_section_level: int = 0  # Heading level (0 = no heading seen yet)

    # Because we have to use a 'do-while' loop, we need to extract the loop
    # contents here because the call to next would otherwise be skipped
    def _parse_line(line_num, line):
        nonlocal current_task, current_section, current_section_level

        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            return
        
        # Try to parse as heading
        heading_data = parse_heading_line(stripped)
        if heading_data:
            current_section = heading_data['text']
            current_section_level = heading_data['level']
            return

        # Try to parse as task line (optimize by checking prefix first)
        if stripped.startswith('- [') and not stripped.startswith('- [['):
            task_data = parse_task_line(line)
            if not task_data:
                return

            # Create new task
            task = Task(
                title=task_data['title'],
                status=task_data['status'],
                tags=task_data['tags'],
                id=task_data['tags'].get('id'),
                indent_level=task_data['indent_level'],
                line_number=line_num,
                raw_lines=[line],
                section=current_section,
                section_level=current_section_level,
            )

            # Determine parent based on indentation
            # Pop stack until we find the right parent level
            while task_stack and task_stack[-1].indent_level >= task.indent_level:
                task_stack.pop()

            if task_stack:
                # This is a child task
                parent = task_stack[-1]
                parent.children.append(task)
            else:
                # This is a root task
                root_tasks.append(task)

            # Push this task onto the stack
            task_stack.append(task)
            current_task = task

        elif current_task and stripped.startswith('-'):
            # This is a note line (indented bullet without checkbox)
            # Only add if indented more than current task
            indent_str = line[:line.find('-')]
            indent_level = calculate_indent_level(indent_str)

            if indent_level > current_task.indent_level:
                current_task.notes.append(f'{indent_level * '    '}{stripped}')
                current_task.raw_lines.append(line)


    # Parse body content (headings and tasks)
    while first_line is not None:
        line_num, line = first_line
        _parse_line(line_num, line)
        first_line = next(lines_iter, None)

    tree = TaskTree(
        tasks=root_tasks,
        file_path=file_path,
    )

    return frontmatter_lines, tree


def write_file(file_path: Path, frontmatter_lines: List[str], tree: TaskTree) -> None:
    """
    Write frontmatter and task tree back to a file.

    Args:
        file_path: Path to write to
        frontmatter_lines: Frontmatter lines (including --- delimiters)
        tree: TaskTree to serialize
    """
    lines = list(frontmatter_lines)
    current_section = None
    current_section_level = 0
    for task in tree.tasks:
        # Detect section change by both text and level (handles same-name headings at different levels)
        if task.section != current_section or task.section_level != current_section_level:
            current_section = task.section
            current_section_level = task.section_level
            if current_section is not None:
                lines.append('')
                lines.append(f'{"#" * current_section_level} {current_section}')
                lines.append('')

        # Task.__str__ auto-handles the recursion so we just need to do one top-level
        lines.append(str(task))

    # Write to file
    file_path.write_text('\n'.join(lines), encoding='utf-8')


# Quick sketch of potential interface for supporting other task systems (like Todoist)
# class StorageContext:
#     tree: TaskTree

# class FileStorageContext(StorageContext):
#     frontmatter: List[str]

# class TaskReader:
#     def read(key: str) -> StorageContext:
#         pass

#     def write(key: str, t: StorageContext):
#         pass

# class FileTaskReader():
#     def read(key: str) -> StorageContext:
#         front, tree = parse_file(Path(key))
#         return FileStorageContext(tree, front)
    
#     def write(key: str, t: FileStorageContext):
#         write_file(Path(key), t.frontmatter, t.tree)