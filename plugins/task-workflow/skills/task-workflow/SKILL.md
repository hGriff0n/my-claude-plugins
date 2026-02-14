---
name: task-workflow
description: Personal task management in markdown TASKS.md files with hierarchical tasks, metadata tags (due dates, estimates, blockers), and context-aware file resolution. Use when working with tasks - (1) Creating/adding tasks with metadata, (2) Listing/filtering tasks by status, due date, or tags, (3) Updating task metadata or blocking relationships, (4) Initializing task tracking, (5) Managing task hierarchies with parent/child relationships, (6) Querying task status, blockers, or dependencies. Handles stub tasks (placeholders), atomic tasks (no subtasks), and automatic context resolution (searches upward for TASKS.md).
---
# Task Workflow

Manage personal tasks in markdown-based TASKS.md files with rich metadata and context awareness.

## Quick Start

**Create new TASKS.md:**

```bash
python3 tasks.py file create --path /path/to/directory
```

**Add a task:**

```bash
python3 tasks.py add "Fix parser bug" --due tomorrow --estimate 2h
```

**List tasks:**

```bash
python3 tasks.py list --due this-week --atomic
```

**Update task:**

```bash
python3 tasks.py update <task-id> --status in-progress --estimate 4h
```

**Archive completed tasks:**

```bash
python3 tasks.py archive --older-than 30
```

## Natural Language Usage

When the user expresses task intent in natural language:

1. **Parse intent** - Extract title, due date, estimate, blockers
2. **Execute CLI** - Run appropriate `tasks.py` command from `scripts/` directory
3. **Report result** - Show task ID and confirmation

**Examples:**

- "Add task: Implement auth, due Monday, 8h estimate" → `tasks.py add "Implement auth" --due 2026-02-17 --estimate 8h`
- "Show me tasks due this week" → `tasks.py list --due this-week`
- "Mark task abc123 as in progress" → `tasks.py update abc123 --status in-progress`
- "What's blocking task xyz?" → `tasks.py list blockers xyz`
- "Archive old completed tasks" → `tasks.py archive --older-than 30`

## Task Format

Tasks are markdown checklist items with emoji/hashtag tags:

```markdown
- [ ] Task title 📅 2026-02-15 #estimate:4h 🆔 abc123 #stub
   Optional notes indented
```

**Key tags:**
- `🆔 <id>` - Unique 6-char ID (auto-generated)
- `📅 <date>` - Due date (YYYY-MM-DD)
- `#estimate:<duration>` - Time estimate (2h, 30m, 1d)
- `⛔ <id>` - Blocked by task ID
- `#stub` - Placeholder needing breakdown
- `➕ <date>` - Created date
- `✅ <date>` - Completed date (when status=done)

**Hierarchy:**

```markdown
- [ ] Parent task 🆔 parent1 #stub
    - [ ] Subtask 1 🆔 child1
    - [ ] Subtask 2 🆔 child2
```

Adding a child removes `#stub` from parent automatically.

## Context Resolution

Files are auto-discovered in this order:

1. Search upward from current directory for `TASKS.md` or `01 TASKS.md`
2. Stop at vault boundary (VAULT_ROOT environment variable)
3. Override with `--file <path>` or `--all` flag to show all vault tasks

## Commands

All commands from `scripts/` directory. Full reference: see [CLI-REFERENCE.md](CLI-REFERENCE.md)

**Essential commands:**

```bash
# Add task
tasks.py add "title" [--due <date>] [--estimate <time>] [--blocked-by <id>] [--parent <id>] [--section <name>]

# List tasks
tasks.py list [--all|--atomic] [--status open|in-progress|done] [--due today|this-week|overdue] [--blocked] [--stub] [--tag <name>]
tasks.py list blockers <id>

# Update task
tasks.py update <id> [--status open|in-progress|done] [--due <date>] [--estimate <time>] [--blocked-by <id>] [--unblock <id>] [--title <text>] [--atomic]

# Archive completed tasks
tasks.py archive [--older-than <days>] [--dry-run]

# Manage cache
tasks.py cache init [--exclude <dirs>]
tasks.py cache refresh [--exclude <dirs>]

# Create new TASKS.md
tasks.py file create --path <path> [--force]
```

**Date parsing:**
- Absolute: `2026-02-15`, `2026-02-15`
- Relative: `today`, `tomorrow`, `friday`, `next monday`

**Duration parsing:**
- Hours: `2h`, `4h`
- Minutes: `30m`, `90m`
- Days: `1d`, `2d`

## Advanced Workflows

### Stub Expansion

When user says "expand task <id>":
1. Read task title
2. Suggest logical subtasks
3. Add subtasks as children with `--parent <id>`
4. Parent's `#stub` removed automatically

### Blocking Management

Manage task dependencies:

- "Add task: Deploy after abc123 is done" → `tasks.py add "Deploy" --blocked-by abc123`
- "What's blocking xyz?" → `tasks.py list blockers xyz`
- "Remove blocker from abc123" → `tasks.py update abc123 --unblock <blocker-id>`

### Smart Filtering

Common filter combinations:

- Actionable tasks: `--atomic --status open --due this-week` (leaf tasks due soon)
- Blocked tasks: `--blocked` (waiting on dependencies)
- In-progress work: `--status in-progress`
- Planning queue: `--stub` (tasks needing breakdown)

## File Structure

```
TASKS.md structure:
---
frontmatter
---
# Tasks

## Open
### Interrupts    (urgent, --global tasks)
### Active        (in progress)
### Planned       (queued)

## Closed         (completed tasks)
```

Tasks added to Open section by default. Marking a task with `--status done` adds completion date and unblocks dependent tasks.

**Scripts location:** `${CLAUDE_PLUGIN_ROOT}/scripts/`
- `tasks.py` - Main CLI
- `cache.py` - Task cache management
- `archive.py` - Archive old tasks
- `models.py` - Task data models
- `parser.py` - Task tree parsing
- `utils.py` - Date/duration parsing

**References:**
- Full CLI options: [CLI-REFERENCE.md](CLI-REFERENCE.md)
- Task schema spec: [tasks-doc.md](tasks-doc.md)
- Tag specification: [tags.md](efforts/workflow/docs/tags.md)
