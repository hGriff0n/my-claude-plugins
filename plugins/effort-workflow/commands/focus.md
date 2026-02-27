---
description: Focus an existing effort.
argument-hint: "<name>"
allowed-tools: mcp__vault-mcp__effort_focus, mcp__vault-mcp__effort_list, Skill
---

Set focus to an existing effort, then spawn a new Claude Code session.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name.

2. Call the `effort_focus` MCP tool with `name=<name>`. The response includes the effort's `path`.

3. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
