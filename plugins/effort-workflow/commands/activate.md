---
description: Mark an effort active and focus it.
argument-hint: "<name>"
allowed-tools: Bash, mcp__vault-mcp__effort_list, mcp__vault-mcp__effort_scan, mcp__vault-mcp__effort_focus, Skill
---

Activate an effort by moving it from the backlog to active, then spawn a new session.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name before proceeding.

2. Move the effort directory from backlog to active:

```bash
mv "$VAULT_ROOT/efforts/__backlog/<name>" "$VAULT_ROOT/efforts/<name>"
```

If the effort is already at `$VAULT_ROOT/efforts/<name>` (already active), skip the move.

3. Call the `effort_scan` MCP tool to re-discover efforts after the directory move.

4. Call the `effort_focus` MCP tool with `name=<name>`.

5. Invoke `/windows:spawn-session` with `$VAULT_ROOT/efforts/<name>` to open a new tab.
