---
description: Add a new task to TASKS.md with optional metadata (due date, estimate, blockers, parent)
argument-hint: "<title> [--due <date>] [--estimate <time>] [--blocked-by <id>] [--parent <id>]"
allowed-tools: mcp__vault-mcp__task_add, Bash
---

Add a task using the `task_add` MCP tool.

## Resolving the target file

If the user provides `--file <path>`, use that path directly.

Otherwise, check for `01 TASKS.md` in the current working directory:

```bash
ls "$PWD/01 TASKS.md" 2>/dev/null
```

If found, use `$PWD/01 TASKS.md` as the `file_path`. If not found, stop and tell the user: "No `01 TASKS.md` found in the current directory. Navigate to an effort directory or use `--file <path>`."

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

If the user provides natural language instead of flags, parse their intent:
- "Fix parser bug, due tomorrow, 2h estimate" → title="Fix parser bug", due="tomorrow", estimate="2h"
- "Implement auth after abc123 is done" → title="Implement auth", blocked_by="abc123"

Report the task ID and confirmation after adding.
