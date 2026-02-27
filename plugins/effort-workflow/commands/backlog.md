---
description: Move an effort to the backlog.
argument-hint: "<name>"
allowed-tools: Bash, mcp__vault-mcp__effort_list, mcp__vault-mcp__effort_scan
---

Move an effort to the backlog by relocating its directory under `__backlog/`.

## Steps

1. If the user provides a partial or fuzzy name, call `effort_list` to find the matching effort and confirm the exact name before proceeding.

2. Ensure the backlog directory exists and move the effort:

```bash
mkdir -p "$VAULT_ROOT/efforts/__backlog"
mv "$VAULT_ROOT/efforts/<name>" "$VAULT_ROOT/efforts/__backlog/<name>"
```

If the effort is already under `__backlog/`, report that it is already in the backlog.

3. Call the `effort_scan` MCP tool to re-discover efforts after the directory move.

4. Confirm the effort has been moved to the backlog.
