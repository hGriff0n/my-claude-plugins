---
description: Get the currently focused effort.
allowed-tools: Bash
---

Query the current focused effort using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/skills/effort-workflow/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/effort-workflow/scripts/efforts.py" focus-get
```

This command returns the name of the currently focused effort, or empty/null if no effort is focused.

**Use cases:**
- Determine current context before running other commands
- Integration with other skills that need to know the active effort
- Programmatic access to focus state
