# Task Workflow Skill

**A recursive task management system for Clawdbot that supports hierarchical task trees, tag-based metadata, and multi-context TASKS.md files.**

---

## 🎯 What This Skill Does

This skill implements the task workflow system defined in `VAULT_ROOT/efforts/workflow/docs/tasks-doc.md`. It provides:

- **Recursive task trees** - Organize work from high-level releases down to atomic tasks
- **Rich metadata** - Track IDs, due dates, estimates, blocking relationships, and more
- **Multi-context support** - Separate `TASKS.md` files per effort/project
- **Emoji-first tags** - Beautiful, readable task metadata (🆔, 📅, ⛔)
- **Automated workflows** - Parent propagation, blocking resolution, metadata inference

---

## 📁 Installation

This skill is located at:
```
CLAUDE_PLUGIN_DIR/skills/task-workflow/
```

No additional dependencies required (uses standard Python 3).

---

## 🚀 Phase 1 Status (Core Infrastructure)

✅ **Completed:**
- [x] Skill directory structure created
- [x] `utils.py` - Date parsing, UUID generation, duration handling
- [x] `metadata.py` - Tag extraction/manipulation (emoji + hashtag)
- [x] `parser.py` - Recursive markdown task tree parser
- [x] `context.py` - TASKS.md resolution and caching
- [x] Unit tests for all core modules
- [x] Manual testing passed

🔜 **Next (Phase 2):**
- [ ] `tasks.py` CLI with add/list/update commands
- [ ] `init.py` for creating new TASKS.md files
- [ ] SKILL.md with natural language triggers

---

## 📝 Task Schema

### Basic Syntax

```markdown
- [ ] Task Title 🆔 abc123 📅 2026-02-15 #estimate:4h
   - Freeform notes about the task
   - Implementation details
   - [ ] Subtask 1 🆔 def456
   - [ ] Subtask 2 🆔 ghi789
```

### Checkbox States
- `- [ ]` → Open/todo
- `- [/]` → In progress
- `- [x]` → Completed

### Supported Tags

| Tag | Emoji | Example | Description |
|-----|-------|---------|-------------|
| `#id:<uuid>` | 🆔 | `🆔 a7f3c2` | Unique task identifier (auto-generated) |
| `#b:<uuid>` | ⛔ | `⛔ abc123` | Blocking task IDs (comma-separated) |
| `#created:<date>` | ➕ | `➕ 2026-02-10` | Creation date (auto-generated) |
| `#due:<date>` | 📅 | `📅 2026-03-15` | Due date (ISO 8601) |
| `#completed:<date>` | ✅ | `✅ 2026-02-11` | Completion date (auto-generated) |
| `#estimate:<duration>` | - | `#estimate:4h` | Estimated time (e.g., 2h, 30m, 1d) |
| `#actual:<duration>` | - | `#actual:3h30m` | Actual time spent |
| `#stub` | - | `#stub` | Unfinished/unexpanded task |
| `#routine:<name>` | - | `#routine:weekly` | Spawned from routine |

**Note:** Emoji tags are preferred for readability. Tags without emoji equivalents use `#tag:value` format.

---

## 🗂️ File Structure

```
skills/task-workflow/
├── SKILL.md                    # Skill triggers (Phase 2)
├── README.md                   # This file
├── scripts/
│   ├── utils.py                ✅ Date/UUID/duration utilities
│   ├── metadata.py             ✅ Tag extraction/manipulation
│   ├── parser.py               ✅ Recursive markdown parser
│   ├── context.py              ✅ TASKS.md resolution + cache
│   ├── tasks.py                🔜 Main CLI (Phase 2)
│   ├── init.py                 🔜 Initialize TASKS.md (Phase 2)
│   ├── inference.py            🔜 Auto-metadata (Phase 4)
│   └── completion.py           🔜 Completion workflows (Phase 3)
├── assets/
│   └── templates/
│       └── TASKS.md            🔜 Template (Phase 2)
├── references/
│   └── task-schema.md          🔜 Full schema spec (Phase 2)
└── tests/
    ├── test_parser.py          ✅ Parser tests
    ├── test_metadata.py        ✅ Metadata tests
    └── test_utils.py           ✅ Utils tests
```

---

## 🔧 Core Modules (Phase 1)

### `utils.py`
**Purpose:** Shared utilities for date parsing, UUID generation, and duration handling.

**Key functions:**
- `generate_task_id(length=6)` - Generate 6-8 char hex UUID
- `parse_date(date_str)` - Parse dates (ISO, "today", "Friday", "in 3 days", etc.)
- `parse_duration(duration_str)` - Parse durations (2h, 30m, 1d, 2h30m)
- `duration_to_minutes(duration_str)` - Convert to total minutes
- `increment_duration(base, increment)` - Add durations
- `check_due_date(due, check_type)` - Check if due today/this-week/overdue

**Example:**
```python
from utils import generate_task_id, parse_date

task_id = generate_task_id()  # → "a7f3c2"
due_date = parse_date("next Friday")  # → "2026-02-14"
```

### `metadata.py`
**Purpose:** Extract and manipulate task metadata tags (both `#tag:value` and emoji formats).

**Key functions:**
- `extract_tags(text)` - Extract all tags → dict
- `strip_tags(text)` - Remove tags, return clean title
- `format_tag(tag_name, value)` - Format single tag (emoji if available)
- `format_tags(tags)` - Format all tags in priority order
- `update_tag(text, tag_name, new_value)` - Update/remove tag
- `add_blocker(text, blocker_id)` - Add blocking task
- `remove_blocker(text, blocker_id)` - Remove blocker

**Example:**
```python
from metadata import extract_tags, format_tags

text = "Task 🆔 abc123 📅 2026-02-15 #estimate:4h"
tags = extract_tags(text)  # → {'id': 'abc123', 'due': '2026-02-15', 'estimate': '4h'}

new_tags = {'id': 'xyz789', 'due': '2026-03-01'}
formatted = format_tags(new_tags)  # → "🆔 xyz789 📅 2026-03-01"
```

### `parser.py`
**Purpose:** Parse recursive markdown task trees into structured data.

**Key classes:**
- `Task` - Single task with title, status, tags, notes, children
- `TaskTree` - Collection of tasks from a file

**Key functions:**
- `parse_tasks(content, file_path)` - Parse markdown → TaskTree
- `format_task(task, indent_level)` - Format Task → markdown
- `format_tree(tree, include_sections)` - Format TaskTree → full markdown

**Example:**
```python
from parser import parse_tasks

content = """
- [ ] Parent task 🆔 p1
   - [ ] Child 1 🆔 c1
   - [x] Child 2 🆔 c2
"""

tree = parse_tasks(content)
print(tree.tasks[0].title)  # → "Parent task"
print(len(tree.tasks[0].children))  # → 2
```

### `context.py`
**Purpose:** Resolve which TASKS.md file to use based on working directory, and manage task cache.

**Key functions:**
- `resolve_tasks_file(cwd, force_global)` - Find nearest TASKS.md
- `get_global_tasks_file()` - Get VAULT_ROOT/TASKS.md
- `find_all_tasks_files()` - Find all TASKS.md in workspace
- `rebuild_cache()` - Rebuild task index cache
- `check_id_collision(task_id)` - Check if ID already exists

**Key class:**
- `TaskCache` - JSON-based cache for fast cross-file lookups

**Example:**
```python
from context import resolve_tasks_file
from pathlib import Path

# From efforts/workflow directory
effort_dir = VAULT_ROOT / "efforts" / "workflow"
tasks_file = resolve_tasks_file(effort_dir)
# → VAULT_ROOT/efforts/workflow/01 TASKS.md
```

---

## 🧪 Testing

Phase 1 includes comprehensive unit tests:

```bash
# Run all tests (requires pytest)
python3 -m pytest tests/ -v

# Manual testing without pytest
python3 tests/test_parser.py
python3 tests/test_metadata.py
python3 tests/test_utils.py
```

**Test coverage:**
- ✅ Tag extraction (emoji + hashtag)
- ✅ Date parsing (ISO, keywords, relative, day names)
- ✅ Duration parsing (hours, minutes, days, mixed)
- ✅ Recursive task tree parsing
- ✅ Parent/child relationships
- ✅ Freeform notes preservation
- ✅ Task formatting back to markdown
- ✅ Context resolution algorithm

---

## 📚 Design Decisions

### 1. Emoji-First Tags
**Decision:** Prefer emoji tags (🆔, 📅, ⛔) over hashtags for better readability.
- Tags WITH emoji equivalent → use emoji (`🆔 abc123`)
- Tags WITHOUT emoji → use hashtag (`#estimate:4h`)

### 2. JSON Cache (Not SQLite)
**Decision:** Use single JSON file at `~/.cache/tooling/tasks/cache.json` for task index.
- Simple, portable, no external dependencies
- Fast enough for expected task counts (<10k)
- Can optimize to SQLite later if needed

### 3. Stub Default Behavior
**Decision:** New tasks default to `#stub` unless explicitly atomic.
- Adding a child removes `#stub` from parent
- Explicit `tasks.py update <id> --atomic` to mark as non-stub

### 4. 3-Space Indentation
**Decision:** Use 3-space indents for subtasks (Obsidian default for task lists).
- Matches Obsidian's behavior
- Consistent with user's existing workflow

---

## 🎯 Next Steps (Phase 2)

1. **Create `tasks.py` CLI** with commands:
   - `tasks.py add <title> [options]`
   - `tasks.py list [filters]`
   - `tasks.py update <id> [options]`

2. **Create `init.py`** to generate TASKS.md from template

3. **Write SKILL.md** with natural language triggers

4. **Create TASKS.md template** in `assets/templates/`

5. **Manual integration testing** with real TASKS.md files

---

## 📖 References

- **Spec:** `VAULT_ROOT/efforts/workflow/docs/tasks-doc.md`
- **Tags:** `VAULT_ROOT/efforts/workflow/docs/tags.md`
- **Implementation Plan:** `VAULT_ROOT/efforts/workflow/task-workflow-skill-plan.md`

---

**Phase 1 Status:** ✅ **COMPLETE** - Ready for review!
