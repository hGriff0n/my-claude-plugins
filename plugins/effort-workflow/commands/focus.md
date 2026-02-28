---
description: Focus an existing effort.
argument-hint: "<name>"
allowed-tools: mcp__vault-mcp__effort_list, Skill
---

Focus an effort by spawning a new Claude Code session in its directory.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name and path.

2. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
