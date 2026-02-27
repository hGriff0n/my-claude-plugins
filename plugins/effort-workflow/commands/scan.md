---
description: Rebuild effort tracking state from the efforts folder.
allowed-tools: mcp__vault-mcp__effort_scan
---

Rebuild effort state by calling the `effort_scan` MCP tool (no parameters).

The tool re-scans the `$VAULT_ROOT/efforts/` directory structure and returns:
- `active` — list of active effort names (top-level dirs with CLAUDE.md)
- `backlog` — list of backlog effort names (dirs under `__backlog/` with CLAUDE.md)

Report the discovered efforts.
