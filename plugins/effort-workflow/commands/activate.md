---
description: Mark an effort active and focus it.
argument-hint: "<name>"
allowed-tools: mcp__vault-mcp__effort_list, mcp__vault-mcp__effort_move, Skill
---

Promote an effort from the backlog to active, then spawn a new session.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name before proceeding.

2. Call the `effort_move` MCP tool with `name=<name>` and `status="active"` to move the effort from backlog to active. The response includes the effort `path`.

3. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
