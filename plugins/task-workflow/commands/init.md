---
description: Create a new TASKS.md file from template in the specified directory
argument-hint: "<path> [--force]"
allowed-tools: Bash, Read
---

Create a new TASKS.md file using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" file create --path $ARGUMENTS
```

**Available options:**

| Option | Argument | Description |
|--------|----------|-------------|
| `--path` | `<path>` | Target path (file or directory) — **required** |
| `--force` | - | Overwrite existing file |

If the user just provides a directory path without `--path`, prepend it automatically:
- `/task-workflow:init ~/projects/myapp` becomes: `file create --path ~/projects/myapp`
- `/task-workflow:init . --force` becomes: `file create --path . --force`

Report the created file path on success.
