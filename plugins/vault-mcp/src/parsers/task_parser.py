"""
Parser for TASKS.md files.

Adapted from task-workflow/scripts/parser.py.

Main API:
    parse_file(path)  → TaskTree
    write_file(path, tree)  → None

The parser uses the SectionBlock structure to preserve the exact heading
order from the original file. write_file serialises back through formatting.py
so the canonical tag format is always applied on write-back.
"""

import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from models.task import CachedFile, SectionBlock, Task, TaskTree
from utils.formatting import EMOJI_TO_TAG, render_tags

# File names recognised as TASKS files (case-sensitive)
TASK_FILE_NAMES = frozenset({"TASKS.md", "01 TASKS.md"})

# Checkbox char → status
_CHECKBOX_STATUS = {
    "x": "done",
    "/": "in-progress",
}


# ---------------------------------------------------------------------------
# Low-level parsers
# ---------------------------------------------------------------------------

def _parse_checkbox(char: str) -> str:
    return _CHECKBOX_STATUS.get(char.strip().lower(), "open")


def _indent_level(indent_str: str) -> int:
    """Convert a leading-whitespace string to a 0-based indent level."""
    spaces = len(indent_str.replace("\t", "    "))
    return spaces // 4


def split_tags(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Split a task content string into (title, tags).

    Tags are always at the end of the line; we find the earliest tag position
    and split there. Supports both emoji and #hashtag formats.

    Wiki-links ([[...]]) are masked before scanning so that internal ``#``
    (section) and ``^`` (block) references are not mistaken for tags.

    A negative lookahead prevents one emoji tag from greedily consuming the
    next emoji as its value (e.g. ``🆔 ➕ 2026-02-25`` won't treat ➕ as the ID).
    """
    tags: Dict[str, str] = {}
    earliest = len(text)
 
    # Mask wiki-links with equal-length spaces so positions stay aligned
    masked = re.sub(r"\[\[.*?\]\]", lambda m: " " * len(m.group()), text)
 
    emoji_pattern = "|".join(re.escape(e) for e in EMOJI_TO_TAG)
    pattern = rf"(?:#([\w/-]+):|({emoji_pattern})\s+)(\S+)|#([\w/-]+)"

    for m in re.finditer(pattern, masked):
        if m.group(1):          # #tag:value
            tags[m.group(1)] = m.group(3)
        elif m.group(2):        # emoji value
            tags[EMOJI_TO_TAG[m.group(2)]] = m.group(3)
        elif m.group(4):        # #tag  (no value)
            tags[m.group(4)] = ""
        earliest = min(earliest, m.start())

    return text[:earliest].strip(), tags


def _parse_task_line(line: str) -> Optional[dict]:
    """Return task dict or None if line is not a task."""
    m = re.match(r"^(\s*)- \[(.)\] (.+)$", line)
    if not m:
        return None
    return {
        "indent_level": _indent_level(m.group(1)),
        "status": _parse_checkbox(m.group(2)),
        "content": m.group(3),
    }


def _parse_heading(stripped: str) -> Optional[Tuple[int, str]]:
    """Return (level, text) or None if line is not a heading."""
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    return level, stripped[level:].strip()


# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

def _extract_frontmatter(
    lines: List[str],
) -> Tuple[List[str], int]:
    """
    Extract YAML frontmatter from the beginning of the file.

    Returns:
        (frontmatter_lines, body_start_index)
        frontmatter_lines includes the --- delimiters verbatim.
        If no frontmatter, returns ([], 0).
    """
    i = 0
    # Skip leading blank lines
    while i < len(lines) and not lines[i].strip():
        i += 1

    if i >= len(lines) or lines[i].strip() != "---":
        return [], 0

    fm: List[str] = []
    fm.append(lines[i])  # opening ---
    i += 1

    while i < len(lines):
        fm.append(lines[i])
        if lines[i].strip() == "---":
            return fm, i + 1
        i += 1

    # Never closed — treat as no frontmatter
    return [], 0


# ---------------------------------------------------------------------------
# Main parse / write API
# ---------------------------------------------------------------------------

def parse_content(content: str, file_path: Optional[Path] = None) -> TaskTree:
    """
    Parse markdown content into a TaskTree.

    Args:
        content: Full file content as a string
        file_path: Source path (stored on tree for reference)

    Returns:
        TaskTree with sections preserving the original heading order
    """
    lines = content.splitlines()
    frontmatter_lines, body_start = _extract_frontmatter(lines)

    sections: List[SectionBlock] = []
    current_section: Optional[SectionBlock] = None
    task_stack: List[Task] = []
    current_task: Optional[Task] = None

    for line_num, line in enumerate(lines[body_start:], start=body_start):
        stripped = line.strip()
        if not stripped:
            continue

        heading = _parse_heading(stripped)
        if heading:
            level, text = heading
            current_section = SectionBlock(heading=text, level=level)
            sections.append(current_section)
            task_stack.clear()
            current_task = None
            continue

        if stripped.startswith("- [") and not stripped.startswith("- [["):
            td = _parse_task_line(line)
            if td is None:
                continue

            title, tags = split_tags(td["content"])
            task = Task(
                title=title,
                status=td["status"],
                tags=tags,
                id=tags.get("id"),
                indent_level=td["indent_level"],
                line_number=line_num,
                section=current_section.heading if current_section else None,
                section_level=current_section.level if current_section else 0,
            )

            # Pop stack to find parent
            while task_stack and task_stack[-1].indent_level >= task.indent_level:
                task_stack.pop()

            if task_stack:
                task_stack[-1].children.append(task)
            else:
                if current_section is None:
                    # Tasks before any heading — create implicit section
                    current_section = SectionBlock(heading="", level=0)
                    sections.append(current_section)
                current_section.tasks.append(task)

            task_stack.append(task)
            current_task = task
            continue

        # Note line: indented bullet without checkbox
        if current_task and stripped.startswith("-"):
            indent_str = line[: line.find("-")]
            note_indent = _indent_level(indent_str)
            if note_indent > current_task.indent_level:
                # Store clean content — strip the leading "- " prefix
                note_text = stripped[2:] if stripped.startswith("- ") else stripped[1:].lstrip()
                current_task.notes.append(note_text)

    return TaskTree(
        file_path=file_path or Path(""),
        sections=sections,
        frontmatter_lines=frontmatter_lines,
    )


def parse_file(file_path: Path) -> TaskTree:
    """Parse a TASKS.md file into a TaskTree."""
    return parse_content(file_path.read_text(encoding="utf-8"), file_path)


def _serialize_task(task: Task, indent_level: int = 0) -> List[str]:
    """Recursively serialize a task and its children to markdown lines."""
    indent = "    " * indent_level
    checkbox = {"done": "[x]", "in-progress": "[/]"}.get(task.status, "[ ]")

    tag_str = render_tags(task.tags)
    if tag_str:
        task_line = f"{indent}- {checkbox} {task.title} {tag_str}"
    else:
        task_line = f"{indent}- {checkbox} {task.title}"

    lines = [task_line]

    note_indent = "    " * (indent_level + 1)
    for note in task.notes:
        lines.append(f"{note_indent}- {note}")

    for child in task.children:
        lines.extend(_serialize_task(child, indent_level + 1))

    return lines


def write_file(file_path: Path, tree: TaskTree) -> None:
    """
    Serialize a TaskTree back to a TASKS.md file.

    Frontmatter is written verbatim. Sections and tasks are rendered using
    the canonical format from utils.formatting.
    """
    lines: List[str] = list(tree.frontmatter_lines)

    for section in tree.sections:
        if section.heading:
            lines.append("")
            lines.append(f"{'#' * section.level} {section.heading}")
            lines.append("")
        for task in section.tasks:
            lines.extend(_serialize_task(task))

    file_path.write_text("\n".join(lines), encoding="utf-8")
