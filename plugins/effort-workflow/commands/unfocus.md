---
description: Shut down the current effort session — log progress, clear focus, and prompt to close tab.
argument-hint: "[name]"
allowed-tools: Bash, Read
---

Shutdown sequence for the current effort session.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

## Steps

1. If the user did not provide a name, get the current focus:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" focus-get
```

Use the printed name as the effort name for the remaining steps.

2. Invoke `/daily:log` to record progress for this session.

3. Clear the focus in the cache:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" focus <name> --unfocus
```

4. Print a message telling the user they can now close this tab:

> Focus cleared for **<name>**. You can close this tab when ready.

5. Invoke `/quit` to exit claude