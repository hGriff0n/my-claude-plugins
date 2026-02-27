---
description: Get the currently focused effort.
allowed-tools: mcp__vault-mcp__effort_get_focus
---

Query the current focused effort using the `effort_get_focus` MCP tool.

Call `effort_get_focus` (no parameters). The response includes:

- `focused` — name of the focused effort, or null if none
- `open_tasks` — list of open/in-progress tasks in the focused effort (if one is focused)

Report the focused effort name, path, and open task summary. If no effort is focused, report that.
