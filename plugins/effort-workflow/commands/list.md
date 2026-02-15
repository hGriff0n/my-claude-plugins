---
description: List active or backlog efforts.
argument-hint: "[--all] [--backlog] [--tasks]"
allowed-tools: Bash, Read
---

List efforts using the effort-workflow CLI.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py`

Run:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/efforts.py" list $ARGUMENTS
```

**Available options:**

| Option | Argument | Description |
|--------|----------|-------------|
| `--all` / `-a` | - | Show active and backlog |
| `--backlog` / `-b` | - | Show backlog only |
| `--tasks` / `-t` | - | Show tasks (placeholder) |

If no arguments are provided, list active efforts only.

If the user provides natural language instead of CLI flags, parse their intent and construct the appropriate command. For example:
- "show backlog projects: `list --backlog`
- "show what I'm currently working on: `list`
