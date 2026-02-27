---
description: Create a new TASKS.md file from template in the specified directory
argument-hint: "<path> [--force]"
allowed-tools: Read, Write
---

Create a new TASKS.md file from the template.

## Steps

1. Determine the target path:
   - If the user provides a directory path, the target is `<path>/TASKS.md`.
   - If the user provides a file path ending in `.md`, use it directly.

2. If the target file already exists and `--force` is not set, report the error and stop.

3. Read the template from `${CLAUDE_PLUGIN_ROOT}/assets/templates/tasks.template.md`.

4. Replace `{{DATE_CREATED}}` with today's date in ISO format (YYYY-MM-DD).

5. Write the result to the target path. Create parent directories if needed.

6. Report the created file path on success.

**Examples:**
- `/task-workflow:init ~/projects/myapp` → creates `~/projects/myapp/TASKS.md`
- `/task-workflow:init . --force` → overwrites `./TASKS.md`
