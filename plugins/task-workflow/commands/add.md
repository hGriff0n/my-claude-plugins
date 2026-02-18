---
description: Add a new task to TASKS.md with optional metadata (due date, estimate, blockers, parent)
argument-hint: "<title> [--due <date>] [--estimate <time>] [--blocked-by <id>] [--parent <id>]"
allowed-tools: Bash, Read
---

Add a task using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" add $ARGUMENTS
```

**Available options:**

| Option | Argument | Description |
|--------|----------|-------------|
| `--due` | `<date>` | Due date (YYYY-MM-DD, today, tomorrow, friday, next monday) |
| `--scheduled` | `<date>` | Scheduled date (YYYY-MM-DD, today, tomorrow, friday, next monday) |
| `--estimate` | `<time>` | Time estimate (2h, 30m, 1d) |
| `--blocked-by` | `<id>` | Task ID this is blocked by |
| `--parent` | `<id>` | Add as subtask under parent |
| `--atomic` | - | Mark as atomic (no #stub tag) |
| `--notes` | `<text>` | Additional notes |
| `--section` | `<name>` | Target section (e.g., "Active", "Planned") |
| `--file` | `<path>` | Force specific TASKS.md file path |

If the user provides natural language instead of CLI flags, parse their intent and construct the appropriate command. For example:
- "Fix parser bug, due tomorrow, 2h estimate" becomes: `add "Fix parser bug" --due tomorrow --estimate 2h`
- "Implement auth after abc123 is done" becomes: `add "Implement auth" --blocked-by abc123`

Report the task ID and confirmation after adding.
