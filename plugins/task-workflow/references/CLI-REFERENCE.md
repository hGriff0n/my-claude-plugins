# CLI Reference - Task Workflow

Complete command-line reference for the task workflow skill.

## Table of Contents

- [Global Options](#global-options) - Options available for all commands
- [tasks.py add](#taskspy-add) - Add new tasks
- [tasks.py list](#taskspy-list) - List and filter tasks
- [tasks.py list blockers](#taskspy-list-blockers) - Show task dependencies
- [tasks.py update](#taskspy-update) - Update task metadata
- [tasks.py archive](#taskspy-archive) - Archive old completed tasks
- [tasks.py cache](#taskspy-cache) - Manage task cache
- [tasks.py file](#taskspy-file) - Manage task files

---

## Global Options

Options available for all commands:

| Option | Argument | Description |
|--------|----------|-------------|
| `--vault` | `<path>` | Vault root directory (default: `C:\Users\ghoop\Desktop\my-brain`) |

---

## tasks.py add

Add a new task to TASKS.md.

### Syntax

```bash
tasks.py add "Task title" [options]
```

### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--due` | `<date>` | Due date (YYYY-MM-DD, today, tomorrow, friday, etc.) |
| `--scheduled` | `<date>` | Scheduled date (YYYY-MM-DD, today, tomorrow, friday, etc.) |
| `--estimate` | `<time>` | Time estimate (e.g., 2h, 30m, 1d) |
| `--blocked-by` | `<uuid>` | UUID of blocking task (creates dependency) |
| `--parent` | `<uuid>` | Add as subtask under parent (removes parent's #stub) |
| `--atomic` | - | Mark as atomic (no #stub tag) |
| `--notes` | `<text>` | Additional notes (indented under task) |
| `--section` | `<name>` | Target section (e.g., "Active", "Planned") |
| `--file` | `<path>` | Force specific TASKS.md file path |

### Examples

**Simple task:**
```bash
tasks.py add "Fix parser bug"
```

**Task with metadata:**
```bash
tasks.py add "Write documentation" --due tomorrow --estimate 4h
```

**Subtask:**
```bash
tasks.py add "Write unit tests" --parent abc123
```

**Blocked task:**
```bash
tasks.py add "Deploy to production" --blocked-by xyz789 --due friday
```

**Task in specific section:**
```bash
tasks.py add "Call client ASAP" --section "Interrupts" --due today
```

**Atomic task (no stub):**
```bash
tasks.py add "Quick fix" --atomic --estimate 30m
```

**Task with notes:**
```bash
tasks.py add "Research authentication" --notes "Check OAuth2 vs JWT"
```

### Behavior

- Generates unique 6-character task ID
- Defaults to `#stub` unless `--atomic` specified
- Auto-removes `#stub` from parent when adding child
- Adds to Open section of TASKS.md
- Resolves target file via context algorithm (see SKILL.md)

### Output

```
✅ Added task: Fix parser bug
   ID: a1b2c3
   Due: 2026-02-11
   File: /home/user/project/TASKS.md
```

---

## tasks.py list

List tasks with optional filtering and display modes.

### Syntax

```bash
tasks.py list [filters] [display-options]
```

### Filters

| Filter | Argument | Description |
|--------|----------|-------------|
| `--all` | - | Show all tasks from entire vault |
| `--atomic` | - | Show only leaf tasks (no children) |
| `--status` | `open\|in-progress\|done` | Filter by status |
| `--due` | `today\|this-week\|overdue` | Filter by due date |
| `--scheduled` | `today\|this-week\|overdue` | Filter by scheduled date |
| `--blocked` | - | Show only blocked tasks (have ⛔ tag) |
| `--stub` | - | Show only stub tasks (have #stub tag) |
| `--section` | `<name>` | Filter by section name |
| `--tag` | `<name>\|<name:value>` | Filter by tag (name or name:value) |
| `--file` | `<path>` | List from specific TASKS.md file |

### Examples

**All root-level tasks (default):**
```bash
tasks.py list
```

**Atomic tasks only:**
```bash
tasks.py list --atomic
```

**Tasks due this week:**
```bash
tasks.py list --due this-week
```

**Blocked tasks with full details:**
```bash
tasks.py list --blocked --full
```

**All tasks in vault:**
```bash
tasks.py list --all
```

**In-progress tasks:**
```bash
tasks.py list --status in-progress
```

**Tasks with specific tag:**
```bash
tasks.py list --tag estimate:4h
```

**Tasks in specific section:**
```bash
tasks.py list --section Active
```

**Stub tasks (need breakdown):**
```bash
tasks.py list --stub
```

**Overdue tasks:**
```bash
tasks.py list --due overdue
```

**Actionable tasks (atomic + due soon):**
```bash
tasks.py list --atomic --due this-week
```

### Output

```
/path/to/TASKS.md
  - [ ] Fix parser bug 🆔 a1b2c3 📅 2026-02-11 #estimate:2h #stub
  - [ ] Write docs 🆔 d4e5f6 #estimate:4h

2 task(s) found.
```

---

## tasks.py list blockers

Show blocking dependencies for a task.

### Syntax

```bash
tasks.py list blockers <id>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `id` | Task ID to check |

### Examples

**Show what blocks a task:**
```bash
tasks.py list blockers abc123
```

### Output

**Task with blockers:**
```
Fix parser bug (abc123) is blocked by:

  - [ ] Write unit tests (xyz789)
  - [x] Setup dev env (def456)

Blocks 2 task(s):

  - Deploy to staging (ghi012)
  - Update documentation (jkl345)
```

**Task without blockers:**
```
Fix parser bug (abc123) has no blockers.
```

---

## tasks.py update

Update existing task metadata.

### Syntax

```bash
tasks.py update <id> [options]
```

### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--status` | `open\|in-progress\|done` | Change status (done adds completion date, unblocks dependents) |
| `--due` | `<date>` | Update due date |
| `--scheduled` | `<date>` | Update scheduled date, used for day-to-day task planning |
| `--estimate` | `<time>` | Update time estimate |
| `--blocked-by` | `<uuid>` | Add blocker dependency |
| `--unblock` | `<uuid>` | Remove blocker dependency |
| `--notes` | `<text>` | Update notes text (empty string to clear) |
| `--title` | `<text>` | Change task title |
| `--atomic` | - | Remove #stub tag (mark as atomic) |

### Examples

**Mark task as in-progress:**
```bash
tasks.py update abc123 --status in-progress
```

**Complete a task:**
```bash
tasks.py update abc123 --status done
```

**Change due date:**
```bash
tasks.py update abc123 --due 2026-02-20
```

**Update estimate:**
```bash
tasks.py update abc123 --estimate 12h
```

**Change title:**
```bash
tasks.py update abc123 --title "New task description"
```

**Add blocker:**
```bash
tasks.py update abc123 --blocked-by xyz789
```

**Remove blocker:**
```bash
tasks.py update abc123 --unblock xyz789
```

**Mark as atomic (remove stub):**
```bash
tasks.py update abc123 --atomic
```

**Update multiple fields:**
```bash
tasks.py update abc123 --status in-progress --due friday --estimate 6h
```

### Behavior

- Searches cache for task ID
- Updates only specified fields
- When status changes to `done`:
  - Adds completion date tag
  - Removes task from blockers of all dependent tasks
  - Reports newly unblocked tasks
- Preserves frontmatter and file structure
- Warns if date/estimate parsing fails

### Output

**Standard update:**
```
Updated: Fix parser bug (abc123)
```

**Completion with unblocking:**
```
Updated: Fix parser bug (abc123)
  Completed: 2026-02-12
  Unblocked 2 task(s):
    - Deploy to staging (ghi012)
    - Update documentation (jkl345)
```

---

## tasks.py archive

Archive old completed tasks to a separate file.

### Syntax

```bash
tasks.py archive [options]
```

### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--file` | `<path>` | Path to TASKS.md (default: auto-resolve) |
| `--older-than` | `<days>` | Archive tasks completed more than N days ago (default: 30) |
| `--dry-run` | - | Preview without modifying files |

### Examples

**Archive tasks older than 30 days:**
```bash
tasks.py archive
```

**Archive tasks older than 90 days:**
```bash
tasks.py archive --older-than 90
```

**Preview archive operation:**
```bash
tasks.py archive --dry-run
```

**Archive specific file:**
```bash
tasks.py archive --file ~/projects/myapp/TASKS.md --older-than 60
```

### Behavior

- Only archives tasks with status `done`
- Moves tasks to `TASKS-ARCHIVE.md` in same directory
- Preserves task hierarchy and metadata
- Updates cache after archiving
- Creates archive file if it doesn't exist

### Output

**Successful archive:**
```
Archived 5 task(s) to /path/to/TASKS-ARCHIVE.md
```

**Dry run:**
```
Dry run: 5 task(s) would be archived:
  - Fix parser bug
  - Write documentation
  - Deploy to staging
  - Update tests
  - Review PR
```

**No tasks to archive:**
```
No tasks to archive.
```

---

## tasks.py cache

Manage the task cache for fast lookups across the vault.

### Subcommands

- `cache init` - Initialize cache from vault
- `cache refresh` - Clear and rebuild cache

---

### cache init

Initialize the cache by scanning the vault for TASKS.md files.

#### Syntax

```bash
tasks.py cache init [options]
```

#### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--exclude` | `<dirs...>` | Directories to skip (space-separated) |

#### Examples

**Initialize cache:**
```bash
tasks.py cache init
```

**Exclude directories:**
```bash
tasks.py cache init --exclude node_modules .git dist
```

#### Output

```
Cache initialized: 12 file(s) loaded, 47 task(s) indexed.
```

---

### cache refresh

Clear and rebuild the entire cache.

#### Syntax

```bash
tasks.py cache refresh [options]
```

#### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--exclude` | `<dirs...>` | Directories to skip (space-separated) |

#### Examples

**Refresh cache:**
```bash
tasks.py cache refresh
```

**Refresh with exclusions:**
```bash
tasks.py cache refresh --exclude archive backup
```

#### Output

```
Cache refreshed: 12 file(s) loaded, 47 task(s) indexed.
```

---

## tasks.py file

Manage TASKS.md files.

### Subcommands

- `file create` - Create new TASKS.md from template

---

### file create

Create a new TASKS.md file from the template.

#### Syntax

```bash
tasks.py file create --path <path> [options]
```

#### Options

| Option | Argument | Description |
|--------|----------|-------------|
| `--path` | `<path>` | Target path (file or directory) - **required** |
| `--force` | - | Overwrite existing file |

#### Examples

**Create in directory:**
```bash
tasks.py file create --path ~/projects/myapp
```

**Create with specific filename:**
```bash
tasks.py file create --path ~/projects/myapp/TASKS.md
```

**Force overwrite:**
```bash
tasks.py file create --path . --force
```

#### Behavior

- If path is a directory, creates `TASKS.md` inside it
- Creates parent directories if needed
- Fills template with current date
- Fails if file exists unless `--force` is used

#### Template Structure

Creates TASKS.md with:

```markdown
---
aliases:
tags:
date created: {{DATE_CREATED}}
last updated: {{DATE_CREATED}}
---
# Tasks

## Open
### Interrupts
### Active
### Planned

## Closed
```

#### Output

```
Created: /home/user/project/TASKS.md
```

---

## Date Parsing

All date arguments support:

**Absolute dates:**
- `2026-02-15`
- `2026-02-15` (ISO 8601)

**Relative dates:**
- `today`
- `tomorrow`
- `friday`, `monday`, etc. (next occurrence)
- `next monday`, `next friday`


---

## Duration Parsing

All estimate/duration arguments support:

**Hours:**
- `2h`, `4h`, `8h`

**Minutes:**
- `30m`, `90m`

**Days:**
- `1d`, `2d`

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (file not found, parse failure, task not found, etc.) |

---

## Common Workflows

### Daily Planning

```bash
# Show what's due today
tasks.py list --due today --status open

# Show actionable tasks
tasks.py list --atomic --status open --due this-week

# Show what you're working on
tasks.py list --status in-progress

# Start working on a task
tasks.py update abc123 --status in-progress

# Complete a task
tasks.py update abc123 --status done
```

### Task Breakdown

```bash
# Add parent stub
tasks.py add "Implement feature X" --estimate 8h

# Add subtasks (auto-removes parent's #stub)
tasks.py add "Design API" --parent abc123 --estimate 2h
tasks.py add "Write tests" --parent abc123 --estimate 3h
tasks.py add "Documentation" --parent abc123 --estimate 1h
```

### Dependency Management

```bash
# Create dependent task
tasks.py add "Deploy" --blocked-by abc123 --due friday

# Show what's blocking a task
tasks.py list blockers abc123

# Show all blocked tasks
tasks.py list --blocked

# Add blocker to existing task
tasks.py update xyz789 --blocked-by abc123

# Remove blocker
tasks.py update xyz789 --unblock abc123
```

### Multi-Context Work

```bash
# List all tasks in vault
tasks.py list --all

# Add to specific file
tasks.py add "Fix bug #42" --file ~/projects/myapp/TASKS.md --estimate 2h

# Create new task file
tasks.py file create --path ~/projects/newapp

# Initialize cache after creating files
tasks.py cache init
```

### Maintenance

```bash
# Archive old completed tasks
tasks.py archive --older-than 30

# Preview archive operation
tasks.py archive --dry-run

# Rebuild cache after manual edits
tasks.py cache refresh
```

---

## Notes

- Task IDs are 6-character base58 strings (no ambiguous characters: 0OIl)
- Collision detection ensures unique IDs across all TASKS.md files
- Cache stored in `~/.cache/task-workflow/cache.json`
- Cache automatically refreshed when files change (mtime check)
- Frontmatter preserved across all operations
- All scripts in `skills/task-workflow/scripts/` directory
- Default vault: `C:\Users\ghoop\Desktop\my-brain` (customizable with `--vault`)
- Task status transitions: `open` → `in-progress` → `done`
- Completing a task automatically unblocks dependent tasks
