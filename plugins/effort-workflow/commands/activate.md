---
description: Mark an effort active and focus it.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Activate an effort using the effort-workflow CLI, then spawn a new Claude Code session in the effort directory.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

## Steps

1. If the user provides a partial or fuzzy name, confirm the exact effort name before running.

2. Run the promote command and capture the printed effort directory path:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" promote $ARGUMENTS
```

The last line of stdout is the effort directory path.

3. Invoke `/windows:spawn-session` with the captured effort directory path to open a new tab.
