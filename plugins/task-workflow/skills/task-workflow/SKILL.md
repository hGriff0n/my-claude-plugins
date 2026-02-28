---
name: task-workflow
description: Personal task management in markdown TASKS.md files with hierarchical tasks, metadata tags (due dates, estimates, blockers), and context-aware file resolution. Use when working with tasks - (1) Creating/adding tasks with metadata, (2) Listing/filtering tasks by status, due date, or tags, (3) Updating task metadata or blocking relationships, (4) Initializing task tracking, (5) Managing task hierarchies with parent/child relationships, (6) Querying task status, blockers, or dependencies. Handles stub tasks (placeholders), atomic tasks (no subtasks), and automatic context resolution (searches upward for TASKS.md).
---
# Task Workflow

Manage personal tasks in markdown-based TASKS.md files with rich metadata and context awareness.

## Quick Start

**Create new TASKS.md:**

Use `/task-workflow:init <path>` — reads template and writes TASKS.md to the specified directory.

**Add a task:**

Uses the `task_add` MCP tool via the vault-mcp server:
- Resolves the target `01 TASKS.md` from the current working directory
- Auto-generates a unique task ID and created date

**List tasks:**

Uses the `task_list` MCP tool with filters (status, due dates, atomic, blocked, stub).

**Update task:**

Uses the `task_update` MCP tool. Setting status to "done" auto-adds completion date and unblocks dependents.

**Archive completed tasks:**

Uses the local archive script — no MCP equivalent for this operation.

## Natural Language Usage

When the user expresses task intent in natural language:

1. **Parse intent** - Extract title, due date, estimate, blockers
2. **Call MCP tool** - Use the appropriate vault-mcp tool (task_add, task_list, task_update, task_blockers)
3. **Report result** - Show task ID and confirmation

**Examples:**

- "Add task: Implement auth, due Monday, 8h estimate" → `task_add` with title, due, estimate (uses `01 TASKS.md` in cwd)
- "Show me tasks due this week" → `task_list` with due_before filter (scoped to cwd `01 TASKS.md` if present)
- "Mark task abc123 as in progress" → `task_update` with status="in-progress"
- "What's blocking task xyz?" → `task_blockers` with task_id
- "Archive old completed tasks" → `tasks.py archive --older-than 30`

## MCP Tools (vault-mcp server)

Most task operations use the vault-mcp MCP server which provides:

- **`task_add`** — Create new tasks with metadata
- **`task_list`** — Filter tasks by status, effort, due dates, flags
- **`task_get`** — Get full task detail by ID
- **`task_update`** — Update task metadata (title, status, dates, blockers)
- **`task_blockers`** — Show blocking relationships (upstream and downstream)
- **`cache_status`** — Show vault cache diagnostics (files, tasks, efforts indexed; last scan)

The server automatically watches for file changes and refreshes its cache.

## Context Resolution

When adding or listing tasks, the target file is resolved from the current working directory:

1. If `--file <path>` is provided, use it directly
2. Otherwise, check for `01 TASKS.md` in cwd — use it if found
3. For `add`: fail if `01 TASKS.md` not found in cwd (no implicit fallback)
4. For `list`: fall back to vault-wide search if `01 TASKS.md` not found in cwd
5. Use `--all` to force a vault-wide search regardless of cwd

## Task Format

Tasks are markdown checklist items with emoji/hashtag tags:

```markdown
- [ ] Task title 📅 2026-02-15 #estimate:4h 🆔 abc123 #stub
   Optional notes indented
```

**Key tags:**
- `🆔 <id>` - Unique 6-char ID (auto-generated)
- `📅 <date>` - Due date (YYYY-MM-DD)
- `⏳ <date>` - Scheduled date (YYYY-MM-DD)
- `#estimate:<duration>` - Time estimate (2h, 30m, 1d)
- `⛔ <id>` - Blocked by task ID
- `#stub` - Placeholder needing breakdown
- `➕ <date>` - Created date (auto-generated)
- `✅ <date>` - Completed date (when status=done)

**Hierarchy:**

```markdown
- [ ] Parent task 🆔 parent1
    - [ ] Subtask 1 🆔 child1 #stub
    - [ ] Subtask 2 🆔 child2 #stub
```

Adding a child removes `#stub` from parent automatically.

## Commands

### MCP-based commands

- **add** — `task_add` MCP tool
- **list** — `task_list` / `task_blockers` MCP tools
- **update** — `task_update` MCP tool
- **reload-cache** — `cache_status` MCP tool (auto-refresh via file watcher)
- **init** — Reads template and writes TASKS.md directly

### Script-based commands

- **archive** — `python3 tasks.py archive` from `scripts/` directory (complex operation without MCP equivalent)

**Date parsing** (handled by MCP server):
- Absolute: `2026-02-15`
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
3. Add subtasks as children with `parent_id=<id>`
4. Parent's `#stub` removed automatically

### Blocking Management

Manage task dependencies:

- "Add task: Deploy after abc123 is done" → `task_add` with blocked_by="abc123"
- "What's blocking xyz?" → `task_blockers` with task_id="xyz"
- "Remove blocker from abc123" → `task_update` with unblock="<blocker-id>"

### Smart Filtering

Common filter combinations via `task_list`:

- Actionable tasks: `atomic=true, status="open", due_before=<end of week>` (leaf tasks due soon)
- Blocked tasks: `blocked=true` (waiting on dependencies)
- In-progress work: `status="in-progress"`
- Planning queue: `stub=true` (tasks needing breakdown)

## File Structure

```
TASKS.md structure:
---
frontmatter
---
### Open
- [ ] Task 1
    - [ ] Subtask 1

### Closed
- [x] Completed task
```

Tasks added to Open section by default. Setting status to "done" adds completion date and unblocks dependent tasks.

**Local scripts** (for archive only): `${CLAUDE_PLUGIN_ROOT}/scripts/`
- `tasks.py` - CLI entry point
- `archive.py` - Archive logic
- `parser.py` - Task tree parsing
- `models.py` - Task data models
- `cache.py` - Local JSON cache
- `utils.py` - Date/duration parsing
