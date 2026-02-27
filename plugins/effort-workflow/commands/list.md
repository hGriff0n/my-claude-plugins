---
description: List active or backlog efforts.
argument-hint: "[--all|-a] [--backlog|-b] [--tasks|-t]"
allowed-tools: mcp__vault-mcp__effort_list
---

List efforts using the `effort_list` MCP tool.

## Parameter mapping

| User flag | MCP parameter |
|-----------|--------------|
| (default, no flags) | `status="active"` |
| `--all` / `-a` | Omit `status` (returns all) |
| `--backlog` / `-b` | `status="backlog"` |
| `--tasks` / `-t` | `include_task_counts=true` |

If the user provides natural language, parse their intent:
- "show backlog projects" → `status="backlog"`
- "show what I'm currently working on" → `status="active"`
- "show all efforts" → omit `status`

Format the results as a readable list, indicating which effort is currently focused (the `is_focused` field). If task counts are included, show them next to each effort.
