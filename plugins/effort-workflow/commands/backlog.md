---
description: Move an effort to the backlog.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Move an effort to backlog using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" relegate $ARGUMENTS
```

If the user provides a partial or fuzzy name, confirm the exact effort name before running.
