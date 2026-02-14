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

**Script:** `${CLAUDE_PLUGIN_ROOT}/skills/review-workflow/scripts/review.py`

Run:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/review-workflow/scripts/review.py" $ARGUMENTS
```

The script will:
1. Load the specified routine file from `areas/__metadata/routines/`
2. Extract session instructions and checklist items
3. Create a TodoWrite task list for the checklist
4. Present the session instructions to guide the conversation
5. Work through each item interactively, marking them complete as you progress
6. Provide a supportive, conversational experience as specified in the routine

**Behavior:**
- Be conversational and supportive, not just a checkbox clicker
- For tracking items (medicine, weight, PT), confirm completion and record data
- For journaling items, engage with meaningful follow-ups
- For review items (calendar, tasks), proactively summarize rather than asking if they looked
- Work sequentially through the checklist
- Use TodoWrite to track progress through the checklist items
