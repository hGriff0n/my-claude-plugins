---
description: Archive old completed tasks to TASKS-ARCHIVE.md
argument-hint: "[--older-than <days>] [--dry-run]"
allowed-tools: Bash, Read
---

Archive completed tasks using the task-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py`

Run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" archive $ARGUMENTS
```

**Available options:**

| Option | Argument | Description |
|--------|----------|-------------|
| `--file` | `<path>` | Path to TASKS.md (default: auto-resolve) |
| `--older-than` | `<days>` | Archive tasks completed more than N days ago (default: 30) |
| `--dry-run` | - | Preview without modifying files |

If no arguments are provided, archives tasks completed more than 30 days ago from the nearest TASKS.md.

Report the number of archived tasks and the archive file path.
