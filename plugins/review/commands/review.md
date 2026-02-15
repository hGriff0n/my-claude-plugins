---
description: Run a structured review routine with interactive checklist.
argument-hint: "<routine-name>"
allowed-tools: Bash, Read, TodoWrite
---

Run a structured review routine from `areas/__metadata/routines/`.

**Routine Discovery:**
Valid routines are markdown files in `areas/__metadata/routines/` with the `n/review` tag in their frontmatter.

**Usage:**
```
/review <routine-name>
```

Example: `/review morning`, `/review evening`, `/review weekly`

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/review.py`

Run:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/review.py" $ARGUMENTS
```

The script will:
1. Load the specified routine file from `areas/__metadata/routines/`
2. Extract session instructions and checklist items
3. Create a TodoWrite task list for the checklist
4. Present the session instructions to guide the conversation
5. Work through each item interactively, marking them complete as you progress
6. Provide a supportive, conversational experience as specified in the routine
7. After all items have been completed, add a summary to the daily file following <reporting/> below

**Behavior:**
- Be conversational and supportive, not just a checkbox clicker
- For tracking items (medicine, weight, PT), confirm completion and record data
- For journaling items, engage with meaningful follow-ups
- For review items (calendar, tasks), proactively summarize rather than asking if they looked
- Work sequentially through the checklist
- Use TodoWrite to track progress through the checklist items

<reporting>
The daily journal file can be found at `VAULT_ROOT/areas/journal/YYYY/MM - MMMM/DD.md`, where `VAULT_ROOT` is an environment variable.

1. **Locate today's daily note**
    - Check default path: `VAULT_ROOT/areas/journal/YYYY/MM - MMMM/DD.md`, where `VAULT_ROOT` is an environment variable
    - Create if it doesn't exist by copying `VAULT_ROOT/areas/__metadata/templates/daily.md`

2. **Analyze the conversation** for:
    - Main topics/tasks worked on

3. **Append a review log** to the "Review" section using the <log_format/> below
    - Be specific about outcomes, not activities
</reporting>

<log_format>
### <name>

[1-2 sentence summary of session. use more sentences if particularly important discussions occur]

#### Checklist
[todo task list]
</log_format>