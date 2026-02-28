---
description: Move an effort to the backlog.
argument-hint: "<name>"
allowed-tools: mcp__vault-mcp__effort_list, mcp__vault-mcp__effort_move
---

Move an effort to the backlog via the vault-mcp server.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name before proceeding.

2. Call the `effort_move` MCP tool with `name=<name>` and `status="backlog"` to move the effort to the backlog.

3. Confirm the effort has been moved to the backlog.
