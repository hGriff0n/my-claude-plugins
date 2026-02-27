---
description: Update an existing task's metadata (status, due date, estimate, blockers, title)
argument-hint: "<task-id> [--status <status>] [--due <date>] [--estimate <time>]"
allowed-tools: mcp__vault-mcp__task_update
---

Update a task using the `task_update` MCP tool.

## MCP tool parameters

The first argument is always the task ID. Call `task_update` with:

| Parameter | Source |
|-----------|--------|
| `task_id` | First argument (required) |
| `title` | From `--title` if provided |
| `status` | From `--status` if provided: "open", "in-progress", or "done" |
| `due` | From `--due` if provided (natural language OK). Pass "" to clear. |
| `scheduled` | From `--scheduled` if provided. Pass "" to clear. |
| `estimate` | From `--estimate` if provided. Pass "" to clear. |
| `blocked_by` | From `--blocked-by` if provided (comma-separated IDs to ADD as blockers) |
| `unblock` | From `--unblock` if provided (comma-separated IDs to REMOVE as blockers) |

Only pass parameters that the user explicitly provides. Omitted parameters are left unchanged.

If the user provides natural language, parse their intent:
- "Mark abc123 as done" → task_id="abc123", status="done"
- "Change due date of abc123 to friday" → task_id="abc123", due="friday"
- "abc123 is blocked by xyz789" → task_id="abc123", blocked_by="xyz789"

Report the update confirmation. When completing a task (status="done"), note that the server automatically adds a completion date and unblocks dependent tasks.
