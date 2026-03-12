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
from typing import Dict, Iterator, List, Optional, Set, Tuple

import emoji

from models.task import CachedFile, SectionBlock, Task, TaskTree
from utils.formatting import EMOJI_TO_TAG, render_tags

# File names recognised as TASKS files (case-sensitive)
TASK_FILE_NAMES = frozenset({"TASKS.md", "01 TASKS.md"})

# Checkbox char → status
_CHECKBOX_STATUS = {
    "x": "done",
    "/": "in-progress",
    "-": "cancelled"
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

# Pre-compiled patterns used by the split / metadata parser
_known_emoji_alt = "|".join(re.escape(e) for e in EMOJI_TO_TAG)
_DATAVIEW_FULL_RE = re.compile(r"[(\[]\s*(\w[\w\s]*?)\s*::\s*(.*?)\s*[)\]]")
_HASHTAG_VAL_RE = re.compile(r"#([\w/-]+):(\S+)")
_HASHTAG_RE = re.compile(r"#([\w/-]+)")

# Matches the first occurrence of any metadata flag at a word boundary:
#   - known emoji (from EMOJI_TO_TAG)
#   - standalone #tag
#   - dataview property (key::...) or [key::...]
_METADATA_START_RE = re.compile(
    rf"(?:^|(?<=\s))(?:(?P<emoji>{_known_emoji_alt})"
    rf"|(?P<hash>#[\w/-])"
    rf"|(?P<dataview>[(\[]\s*\w[\w\s]*?\s*::))",
)


def _bracket_depth_at(text: str, pos: int) -> int:
    """Count unmatched ``(``, ``[`` minus ``)``, ``]`` in *text[:pos]*."""
    depth = 0
    for ch in text[:pos]:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
    return depth


def _find_metadata_start(text: str) -> Optional[int]:
    """
    Find the position where metadata tags begin in *text*.

    Uses a single regex to locate the earliest known-emoji, ``#tag``, or
    dataview property at a word boundary.  For ``#`` matches the bracket/paren
    depth of the prefix is checked so that ``#`` inside ``[[wiki-links]]`` or
    parenthesised text is ignored.
    """
    for m in _METADATA_START_RE.finditer(text):
        if m.group("hash"):
            if _bracket_depth_at(text, m.start()) == 0:
                return m.start()
            continue  # inside brackets — skip this # and keep looking
        return m.start()
    return None


def _is_metadata_token(tok: str) -> bool:
    """Check whether a whitespace-delimited token starts a metadata entry."""
    if tok in EMOJI_TO_TAG:
        return True
    if emoji.is_emoji(tok):
        return True
    if tok.startswith("#"):
        return True
    if tok[0] in "([" and (len(tok) < 2 or tok[1] != "["):
        return True
    return False


def _parse_metadata(tail: str) -> Tuple[Dict[str, str], Set[str]]:
    """
    Parse a metadata tail string into a tag dictionary.

    The tail is split by whitespace into tokens, then each token is classified:

    - Known emoji (``EMOJI_TO_TAG``): next token is the value
    - Unknown emoji: greedy — all following tokens until the next metadata
      token are joined as the value
    - ``#tag`` or ``#tag:value``: single token
    - ``(key::value)`` or ``[key::value]``: single token (dataview property)

    Returns:
        (tags, dataview_tags) — the tag dict and the set of tag names that
        were declared using dataview property syntax.
    """
    tokens = tail.split()
    tags: Dict[str, str] = {}
    dataview_tags: Set[str] = set()
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        # Known emoji → next token is the value
        if tok in EMOJI_TO_TAG:
            tags[EMOJI_TO_TAG[tok]] = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
            continue

        # Dataview property — may span multiple tokens: [ key :: value ]
        if tok[0] in "([" and (len(tok) < 2 or tok[1] != "["):
            closer = ")" if tok[0] == "(" else "]"
            parts = [tok]
            j = i + 1
            while j < len(tokens) and closer not in parts[-1]:
                parts.append(tokens[j])
                j += 1
            dv = _DATAVIEW_FULL_RE.fullmatch(" ".join(parts))
            if dv:
                tags[dv.group(1)] = dv.group(2)
                dataview_tags.add(dv.group(1))
                i = j
                continue

        # Hashtag with or without value
        if tok.startswith("#"):
            m = _HASHTAG_VAL_RE.fullmatch(tok)
            if m:
                tags[m.group(1)] = m.group(2)
                i += 1
                continue
            m = _HASHTAG_RE.fullmatch(tok)
            if m:
                tags[m.group(1)] = ""
                i += 1
                continue

        # Unknown emoji → greedy value until next metadata token
        if emoji.is_emoji(tok):
            i += 1
            val_parts: List[str] = []
            while i < len(tokens) and not _is_metadata_token(tokens[i]):
                val_parts.append(tokens[i])
                i += 1
            tags[tok] = " ".join(val_parts)
            continue

        # Unrecognised token — skip
        i += 1

    return tags, dataview_tags


def split_tags(text: str) -> Tuple[str, Dict[str, str], Set[str]]:
    """
    Split a task content string into (title, tags, dataview_tags).

    A left-to-right scan finds the first metadata flag (known emoji,
    ``#tag`` outside brackets/parens, or dataview property) and splits there.
    The metadata portion is then parsed for known emoji, unknown emoji,
    hashtags, and dataview properties.

    Returns:
        (title, tags, dataview_tags) — dataview_tags is the set of tag names
        that were declared using dataview property syntax.
    """
    split_pos = _find_metadata_start(text)
    if split_pos is None:
        return text.strip(), {}, set()
    tags, dataview_tags = _parse_metadata(text[split_pos:])
    return text[:split_pos].strip(), tags, dataview_tags


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

            title, tags, dataview_tags = split_tags(td["content"])
            task = Task(
                title=title,
                status=td["status"],
                tags=tags,
                dataview_tags=dataview_tags,
                id=tags.get("id"),
                indent_level=td["indent_level"],
                line_number=line_num,
                section=current_section.heading if current_section else None,
                section_level=current_section.level if current_section else 0,
                file_path=file_path,
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
                # Store (relative_indent, text) — relative_indent 1 = directly under task
                note_text = stripped[2:] if stripped.startswith("- ") else stripped[1:].lstrip()
                relative = note_indent - current_task.indent_level
                current_task.notes.append((relative, note_text))

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
    checkbox = next((k for k, v in _CHECKBOX_STATUS.items() if v == task.status), ' ')

    tag_str = render_tags(task.tags, task.dataview_tags)
    if tag_str:
        task_line = f"{indent}- [{checkbox}] {task.title} {tag_str}"
    else:
        task_line = f"{indent}- [{checkbox}] {task.title}"

    lines = [task_line]

    for rel, note_text in task.notes:
        note_indent = "    " * (indent_level + rel)
        lines.append(f"{note_indent}- {note_text}")

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
