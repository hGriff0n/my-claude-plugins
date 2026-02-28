---
description: Create a new effort, mark it active, and focus it.
argument-hint: "<name>"
allowed-tools: mcp__vault-mcp__effort_create, Skill
---

Create a new effort using the vault-mcp server, then spawn a new Claude Code session.

## Steps

1. Call the `effort_create` MCP tool with `name=<name>` to create the effort directory, initialize files, and register it as active. The response includes the effort `path`.

2. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
