---
description: List and filter tasks, or show blockers for a specific task
argument-hint: "[blockers <id>] [--status <status>] [--due <range>] [--atomic] [--all]"
allowed-tools: Bash, Read
---

List tasks or show blockers using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" list $ARGUMENTS
```

**Subcommands:**

- `list` — List tasks with filters
- `list blockers <id>` — Show what blocks a specific task

**Available filters:**

| Filter | Argument | Description |
|--------|----------|-------------|
| `--all` | - | Show all tasks from entire vault |
| `--atomic` | - | Show only leaf tasks (no children) |
| `--status` | `open\|in-progress\|done` | Filter by status |
| `--due` | `today\|this-week\|overdue` | Filter by due date |
| `--scheduled` | `today\|this-week\|overdue` | Filter by scheduled date |
| `--blocked` | - | Show only blocked tasks |
| `--stub` | - | Show only stub tasks needing breakdown |
| `--section` | `<name>` | Filter by section name |
| `--tag` | `<name>\|<name:value>` | Filter by tag |
| `--file` | `<path>` | List from specific TASKS.md file |

**Common combinations:**

- Actionable tasks: `--atomic --status open --due this-week`
- Blocked tasks: `--blocked`
- In-progress work: `--status in-progress`
- Planning queue: `--stub`

If no arguments are provided, run `list` with no filters (shows root-level tasks from nearest TASKS.md).
