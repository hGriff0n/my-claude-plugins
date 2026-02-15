---
description: Create a new effort, mark it active, and focus it.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Create a new effort using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" new $ARGUMENTS
```

If the effort name contains spaces, quote it. After success, invoke `/task-workflow:init <path>` where `<path>` is the newly created effort directory.
