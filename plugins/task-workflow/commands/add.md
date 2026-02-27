---
description: Add a new task to TASKS.md with optional metadata (due date, estimate, blockers, parent)
argument-hint: "<title> [--due <date>] [--estimate <time>] [--blocked-by <id>] [--parent <id>]"
allowed-tools: mcp__vault-mcp__task_add, mcp__vault-mcp__effort_get_focus
---

Add a task using the `task_add` MCP tool.

## Resolving the target file

If the user provides `--file <path>`, use that path directly.

Otherwise, call the `effort_get_focus` MCP tool. If an effort is focused, use its `tasks_file` field as the `file_path`. If no effort is focused, ask the user which TASKS.md file to add to.

## MCP tool parameters

Call `task_add` with:

| Parameter | Source |
|-----------|--------|
| `title` | The task title from user input |
| `file_path` | Resolved as above |
| `section` | From `--section` if provided |
| `status` | From `--status` if provided (default: "open") |
| `due` | From `--due` if provided (natural language OK: "tomorrow", "friday", "next monday") |
| `scheduled` | From `--scheduled` if provided |
| `estimate` | From `--estimate` if provided (e.g., "2h", "30m", "1d") |
| `blocked_by` | From `--blocked-by` if provided (comma-separated task IDs) |
| `parent_id` | From `--parent` if provided |
| `atomic` | True if `--atomic` flag present, otherwise omit |

If the user provides natural language instead of flags, parse their intent:
- "Fix parser bug, due tomorrow, 2h estimate" → title="Fix parser bug", due="tomorrow", estimate="2h"
- "Implement auth after abc123 is done" → title="Implement auth", blocked_by="abc123"

Report the task ID and confirmation after adding.
