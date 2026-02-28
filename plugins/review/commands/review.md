---
description: Run a structured review routine with interactive checklist.
argument-hint: "<routine-name>"
allowed-tools: Bash, TodoWrite, AskUserQuestion, Skill
---

Run a structured review routine from `areas/personal/routines/`.

**Routine Discovery:**
Valid routines are markdown files in `areas/personal/routines/` with the `n/review` tag in their frontmatter.

**Usage:**
```
/review <routine-name>
```

Example: `/review morning`, `/review evening`, `/review weekly`

**Steps:**
1. Read the routine: `obsidian read file=areas/personal/routines/$ARGUMENTS.md`
2. Follow `## Session Instructions` as context
3. Use TodoWrite to build the task list from checklist items, skipping nested items
4. Work through each item conversationally, following nested-item behavior in <nesting/>
5. On completion, follow <reporting/> below

**Behavior:**
- Be conversational and supportive, not just a checkbox clicker
- For tracking items (medicine, weight, PT), confirm completion and record data
- For journaling items, engage with meaningful follow-ups
- For review items (calendar, tasks), proactively summarize rather than asking if they looked
- Work sequentially through the checklist
- Use TodoWrite to track progress through the checklist items

<nesting>
**Nested task items** (indented `- [ ]` children under a parent task) are the sequential steps required to complete that parent. Handle them as follows:

1. When you reach a parent task that has nested `- [ ]` sub-items, do **not** ask about the parent directly — instead, expand its sub-items into the todo list (via `TodoWrite`) so they appear as individual tracked steps alongside the top-level items
2. Walk through each sub-item one at a time, marking it `in_progress` then `completed` in the todo list as the user confirms it
3. Complete each sub-item in the todo list as it's confirmed done
4. Only complete the parent in the todo list once **all** sub-items are marked complete

**Non-task lines** under a checklist item (lines that aren't `- [ ]` items, e.g. plain bullet notes or instructions) are directives for you to act on — not items to ask the user about. Execute them at the appropriate point (e.g. when the parent is being completed).
</nesting>

<reporting>
1. **Analyze the conversation** for:
    - Main topics/tasks worked on

2. **Generate and append a review log** to today's daily note:
    - If the routine file has a `## Report` section, follow its instructions to generate the log content and format
    - Otherwise, use the <log_format/> below as the format
    - Ensure the daily note exists:
      1. `obsidian daily:path` → capture the path
      2. `obsidian file path="<path>"` → if output starts with `Error:`, run `obsidian create path="<path>"`
    - `obsidian daily:append content="<log>"`

3. **Mark habit completed** using the Obsidian CLI on `areas/personal/routines/habits/reviews.md`:
   - Read current entries: `obsidian property:read name=entries file=reviews`
   - Append today's date (`YYYY-MM-DD`) to the list, then convert newline-separated dates to comma-separated
   - Write back: `obsidian property:set name=entries type=list value="<comma-separated dates>" file=reviews`
</reporting>

<log_format>
### <name>

[1-2 sentence summary of session. use more sentences if particularly important discussions occur]

#### Checklist
[todo task list]
</log_format>