---
description: Create a new effort, mark it active, and focus it.
argument-hint: "<name>"
allowed-tools: Bash, Read, Write, mcp__vault-mcp__effort_scan, mcp__vault-mcp__effort_focus, Skill
---

Create a new effort directory, initialize it, then spawn a new Claude Code session.

## Steps

1. Determine the effort directory path: `$VAULT_ROOT/efforts/<name>`

2. Create the directory and initialize files:

```bash
mkdir -p "$VAULT_ROOT/efforts/<name>"
```

3. Read the CLAUDE.md template from `${CLAUDE_PLUGIN_ROOT}/assets/CLAUDE.template.md` and write it to `$VAULT_ROOT/efforts/<name>/CLAUDE.md`.

4. Read the README template from `${CLAUDE_PLUGIN_ROOT}/assets/readme.template.md` and write it to `$VAULT_ROOT/efforts/<name>/README.md`.

5. Call the `effort_scan` MCP tool to discover the new effort.

6. Call the `effort_focus` MCP tool with `name=<name>` to set focus.

7. Invoke `/task-workflow:init <effort directory path>` to create the TASKS.md file.

8. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
