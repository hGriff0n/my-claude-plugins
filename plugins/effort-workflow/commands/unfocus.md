---
description: Clear the current focused effort.
argument-hint: "<name>"
allowed-tools: Bash, Read
---

Clear focus using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" focus $ARGUMENTS --unfocus
```

If the user doesn't specify a name, use the current focused effort