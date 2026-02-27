---
description: List and filter tasks, or show blockers for a specific task
argument-hint: "[blockers <id>] [--status <status>] [--due <range>] [--atomic] [--all]"
allowed-tools: mcp__vault-mcp__task_list, mcp__vault-mcp__task_blockers, mcp__vault-mcp__effort_get_focus
---

List tasks or show blockers using MCP tools.

## Subcommands

### `list blockers <id>`

Call the `task_blockers` MCP tool with `task_id=<id>`. Report upstream (what blocks it) and downstream (what it blocks) relationships.

### `list` (default)

Call the `task_list` MCP tool with filters mapped from arguments.

## Scoping

- If `--all` is provided, omit the `effort` parameter (searches entire vault).
- If `--file <path>` is provided, use `file_path=<path>`.
- Otherwise, call `effort_get_focus` to get the current effort name and pass it as the `effort` parameter to scope results to the focused effort. If no effort is focused, omit the `effort` parameter (vault-wide).

## Filter mapping

| User flag | MCP parameter | Notes |
|-----------|--------------|-------|
| `--status open\|in-progress\|done` | `status` | Default: "open,in-progress" |
| `--atomic` | `atomic=true` | Only leaf tasks |
| `--stub` | `stub=true` | Only stub tasks |
| `--blocked` | `blocked=true` | Only blocked tasks |
| `--due today` | `due_before=<today's date>` | ISO format YYYY-MM-DD |
| `--due this-week` | `due_before=<end of week date>` | Calculate the upcoming Sunday |
| `--due overdue` | `due_before=<yesterday's date>` | Tasks past due |
| `--scheduled today` | `scheduled_on=<today's date>` | Exact match |
| `--scheduled this-week` | `scheduled_before=<end of week date>` | On or before end of week |
| `--file <path>` | `file_path` | Specific file |

**Common combinations:**

- Actionable tasks: `atomic=true, status="open", due_before=<end of week>`
- Blocked tasks: `blocked=true`
- In-progress work: `status="in-progress"`
- Planning queue: `stub=true`

Format results as a readable task list. If no tasks match, report "No tasks found."
