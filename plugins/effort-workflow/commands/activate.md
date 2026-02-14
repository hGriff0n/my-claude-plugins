---
description: Mark an effort active and focus it.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Activate an effort using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/skills/effort-workflow/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/effort-workflow/scripts/efforts.py" promote $ARGUMENTS
```

If the user provides a partial or fuzzy name, confirm the exact effort name before running.
