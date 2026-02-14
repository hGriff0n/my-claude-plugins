---
description: Clear and rebuild the task cache for fast lookups across the vault
argument-hint: "[--exclude <dirs...>]"
allowed-tools: Bash
---

Refresh the task cache using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" cache refresh $ARGUMENTS
```

**Available options:**

| Option | Argument | Description |
|--------|----------|-------------|
| `--exclude` | `<dirs...>` | Directories to skip (space-separated) |

If no arguments are provided, refreshes the entire cache with default settings.

Report the number of files loaded and tasks indexed.
