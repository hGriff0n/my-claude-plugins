---
description: Shut down the current effort session — log progress, clear focus, and prompt to close tab.
argument-hint: "[name]"
allowed-tools: mcp__vault-mcp__effort_get_focus, mcp__vault-mcp__effort_unfocus, Skill
---

Shutdown sequence for the current effort session.

## Steps

1. If the user did not provide a name, call the `effort_get_focus` MCP tool and use the `focused` field as the effort name.

2. Invoke `/daily:log` to record progress for this session.

3. Call the `effort_unfocus` MCP tool to clear focus.

4. Print a message telling the user they can now close this tab:

> Focus cleared for **<name>**. You can close this tab when ready.

5. Invoke `/quit` to exit Claude.
