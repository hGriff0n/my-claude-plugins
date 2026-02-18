---
description: Update an existing task's metadata (status, due date, estimate, blockers, title)
argument-hint: "<task-id> [--status <status>] [--due <date>] [--estimate <time>]"
allowed-tools: Bash, Read
---

Update a task using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" update $ARGUMENTS
```

**First argument must be the task ID.** Then any combination of options:

| Option | Argument | Description |
|--------|----------|-------------|
| `--status` | `open\|in-progress\|done` | Change status (done adds completion date, unblocks dependents) |
| `--due` | `<date>` | Update due date |
| `--scheduled` | `<date>` | Update scheduled date |
| `--estimate` | `<time>` | Update time estimate |
| `--blocked-by` | `<id>` | Add blocker dependency |
| `--unblock` | `<id>` | Remove blocker dependency |
| `--notes` | `<text>` | Update notes (empty string to clear) |
| `--title` | `<text>` | Change task title |
| `--atomic` | - | Remove #stub tag |

If the user provides natural language, parse their intent:
- "Mark abc123 as done" becomes: `update abc123 --status done`
- "Change due date of abc123 to friday" becomes: `update abc123 --due friday`
- "abc123 is blocked by xyz789" becomes: `update abc123 --blocked-by xyz789`

Report the update confirmation. When completing a task, report any newly unblocked tasks.
