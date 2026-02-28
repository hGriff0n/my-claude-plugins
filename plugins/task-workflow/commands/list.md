---
description: List and filter tasks, or show blockers for a specific task
argument-hint: "[blockers <id>] [--status <status>] [--due <range>] [--atomic] [--all]"
allowed-tools: mcp__vault-mcp__task_list, mcp__vault-mcp__task_blockers, Bash
---

List tasks or show blockers using MCP tools.

## Subcommands

### `list blockers <id>`

Call the `task_blockers` MCP tool with `task_id=<id>`. Report upstream (what blocks it) and downstream (what it blocks) relationships.

### `list` (default)

Call the `task_list` MCP tool with filters mapped from arguments.

## Scoping

- If `--all` is provided, omit the `file_path` parameter (searches entire vault).
- If `--file <path>` is provided, use `file_path=<path>`.
- Otherwise, check for `01 TASKS.md` in the current working directory. If found, use `file_path=$PWD/01 TASKS.md`. If not found, omit `file_path` (vault-wide).

## Filter mapping

| User flag | MCP parameter | Notes |
|-----------|--------------|-------|
| `--status open\|in-progress\|done` | `status` | Default: "open,in-progress" |
| `--stub` | `stub=true` | Only stub tasks |
| `--blocked` | `blocked=true` | Only blocked tasks |
| `--due today` | `due_before=<today's date>` | ISO format YYYY-MM-DD |
| `--due this-week` | `due_before=<end of week date>` | Calculate the upcoming Sunday |
| `--due overdue` | `due_before=<yesterday's date>` | Tasks past due |
| `--scheduled today` | `scheduled_on=<today's date>` | Exact match |
| `--scheduled this-week` | `scheduled_before=<end of week date>` | On or before end of week |
| `--file <path>` | `file_path` | Specific file |

**Common combinations:**

- Actionable tasks: `status="open", due_before=<end of week>`
- Blocked tasks: `blocked=true`
- In-progress work: `status="in-progress"`
- Planning queue: `stub=true`

Format results as a readable task list. If no tasks match, report "No tasks found."
