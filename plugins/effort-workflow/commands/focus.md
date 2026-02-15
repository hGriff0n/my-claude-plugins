---
description: Focus an existing effort.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Set focus to an existing effort using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" focus $ARGUMENTS
```

If the user provides a partial or fuzzy name, confirm the exact effort name before running.
