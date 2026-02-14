#!/usr/bin/env python3
"""
Review routine runner for Claude Code.

Parses routine markdown files and outputs instructions for Claude to run
interactive review sessions using TodoWrite for checklist tracking.
"""

import sys
import os
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json


TodoTaskList = List[Dict[str, str]]


def get_vault_root() -> Path:
    """Get vault root from VAULT_ROOT environment variable."""
    vault_root = os.environ.get('VAULT_ROOT')
    if not vault_root:
        print("ERROR: VAULT_ROOT environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return Path(vault_root)


def attempt_get_inline_tags(line: str) -> List[str]:
    """Try to extract an inline array (or single value) for the `tags:` line.

    Returns empty list if tags are in multi-line bullet format.
    """
    # Extract everything after "tags:"
    tags_value = line[5:].strip()  # Remove 'tags:' prefix

    if tags_value.startswith('['):
        # Inline array format: tags: [tag1, tag2]
        return re.findall(r'[\w\/\-]+', tags_value)
    elif tags_value:
        # Single value format: tags: n/review
        return [tags_value]
    else:
        # Multi-line bullet format - return empty list
        return []


def is_review_file(file) -> bool:
    """Parse the file's frontmatter to find the 'n/review' tag."""
    in_frontmatter = False
    tags = []
    in_tags = False
    for line in file:
        line = line.strip()
        if line == '---':
            if in_frontmatter:
                return False
            in_frontmatter = True

        elif in_tags:
            if not line.startswith('-'):
                break
            tags.append(line[2:].strip())

        # Because we strip the whitespace, if the line matches tags exactly
        # we know we are dealing with a multi-line tags string
        elif line == "tags:":
            in_tags = True

        # Otherwise, if it merely starts with "tags", then we have to be
        # dealing with an inline tags array so we can immediately exit
        elif line.startswith('tags:'):
            tags = attempt_get_inline_tags(line)
            break
    
    return 'n/review' in tags


def get_valid_routines(vault_root: Path) -> List[str], Path:
    """Get list of valid routine names (files with n/review tag)."""
    routines_dir = vault_root / "areas" / "__metadata" / "routines"

    if not routines_dir.exists():
        return [], routines_dir

    valid_routines = []
    for file in routines_dir.glob("*.md"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                if is_review_file(f):
                    valid_routines.append(file.stem)
        except Exception:
            continue

    return sorted(valid_routines), routines_dir


def parse_routine_file(routine_path: Path) -> Tuple[Optional[str], Optional[TodoTaskList]]:
    """Parse a routine markdown file and extract instructions and checklist."""
    with open(routine_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split on frontmatter
    parts = content.split('---', 2)
    if len(parts) < 3:
        return None, None

    body = parts[2].strip()

    # Split body into instructions and checklist
    sections = body.split('## Checklist', 1)
    if len(sections) < 2:
        return None, None

    instructions = sections[0].strip()
    checklist_raw = sections[1].strip()

    # Parse checklist items (including nested sub-items)
    checklist_items = []
    lines = checklist_raw.split('\n')

    for line in lines:
        if not line.strip():
            continue

        # Match task items: - [ ] Task text
        # Check indentation to determine if it's a sub-item
        indent_match = re.match(r'^(\s*)- \[([ x\/])\]\s+(.+)$', line)
        if indent_match:
            indent = indent_match.group(1)
            text = indent_match.group(3)

            # Remove markdown bold markers
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)

            # Indent nested items with a visual indicator
            indent_prefix = "  " * (len(indent) // 2) if len(indent) > 0 else ""
            if indent_prefix:
                text = f"{indent_prefix}> {text}"

            checklist_items.append({
                'content': text,
                'status': 'pending',
                'activeForm': text
            })

    return instructions, checklist_items


def generate_todo_json(items: TodoTaskList) -> str:
    """Generate the JSON format for TodoWrite tool."""
    # Add a marker task at the beginning
    items.insert(0, {
        'content': f'Complete review checklist ({len(items)} items)',
        'activeForm': f'Completing review checklist ({len(items)} items)',
        'status': 'in_progress'
    })

    return json.dumps(items, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='Run a structured review routine with interactive checklist.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'routine',
        help='Name of the routine to run (e.g., morning, evening, weekly)'
    )

    args = parser.parse_args()
    routine_name = args.routine.lower()

    # Get vault root
    vault_root = get_vault_root()

    # Construct routine file path and verify it is a valid review routine
    valid_routines, routines_dir = get_valid_routines(vault_root)
    routine_path = vault_root / "areas" / "__metadata" / "routines" / f"{routine_name}.md"
    if routine_name not in valid_routines:
        if not routines_dir.exists():
            print(f"ERROR: Routine directory not found: {routines_dir}", file=sys.stderr)
        else:
            if not routine_path.exists():
                print(f"ERROR: Routine file not found: {routine_path}", file=sys.stderr)
            else:
                print(f"ERROR: '{routine_name}' is not a valid review routine (missing 'n/review' tag)", file=sys.stderr)
            print(f"\nAvailable routines: {', '.join(valid_routines)}", file=sys.stderr)
        return 1

    # Parse the routine file
    instructions, checklist = parse_routine_file(routine_path)

    if not instructions or not checklist:
        print(f"ERROR: Failed to parse routine file: {routine_path}", file=sys.stderr)
        print("Expected format: frontmatter, session instructions, ## Checklist section", file=sys.stderr)
        sys.exit(1)

    # Output instructions for Claude
    divider = "=" * 80
    print(f"REVIEW ROUTINE: {routine_name.upper()}")
    print(divider)
    print()
    print("SESSION INSTRUCTIONS:")
    print(instructions)
    print()
    print(divider)
    print()
    print("NEXT STEPS:")
    print("1. Use TodoWrite to create the checklist (JSON below)")
    print("2. Work through each item conversationally and supportively")
    print("3. Mark items complete as you progress using TodoWrite")
    print("4. Follow the session instructions above for tone and approach")
    print()
    print("TODO JSON FOR TodoWrite:")
    print(generate_todo_json(checklist))
    print()
    print(divider)
    return 0



if __name__ == "__main__":
    sys.exit(main())
