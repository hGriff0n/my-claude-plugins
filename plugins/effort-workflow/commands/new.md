---
description: Create a new effort, mark it active, and focus it.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Create a new effort using the effort-workflow CLI, initialize task tracking, then spawn a new Claude Code session in the effort directory.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

## Steps

1. If the effort name contains spaces, quote it.

2. Run the new effort command and capture the printed effort directory path:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" new $ARGUMENTS
```

The last line of stdout is the effort directory path.

3. Invoke `/task-workflow:init <path>` where `<path>` is the captured effort directory path.

4. Invoke `/windows:spawn-session` with the effort directory path to open a new tab.
