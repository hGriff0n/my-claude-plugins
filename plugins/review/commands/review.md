---
description: Run a structured review routine with interactive checklist.
argument-hint: "<routine-name>"
allowed-tools: Bash, Read, TodoWrite, Write, Edit, AskUserQuestion, Skill
---

Run a structured review routine from `areas/__metadata/routines/`.

**Routine Discovery:**
Valid routines are markdown files in `areas/__metadata/routines/` with the `n/review` tag in their frontmatter.

**Usage:**
```
/review <routine-name>
```

Example: `/review morning`, `/review evening`, `/review weekly`

**Steps:**
1. Read `VAULT_ROOT/areas/__metadata/routines/$ARGUMENTS.md`, where `VAULT_ROOT` is an environment variable
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
3. Mark each sub-item `[x]` in the file as it's confirmed done
4. Only mark the parent `[x]` (and complete it in the todo list) once **all** sub-items are marked complete

**Non-task lines** under a checklist item (lines that aren't `- [ ]` items, e.g. plain bullet notes or instructions) are directives for you to act on — not items to ask the user about. Execute them at the appropriate point (e.g. when the parent is being completed).
</nesting>

<reporting>
The daily journal file can be found at `VAULT_ROOT/areas/journal/YYYY/MM - MMMM/DD.md`

1. **Locate today's daily note**
    - Check default path: `VAULT_ROOT/areas/journal/YYYY/MM - MMMM/DD.md`
    - Create if it doesn't exist by copying `VAULT_ROOT/areas/__metadata/templates/daily.md`

2. **Analyze the conversation** for:
    - Main topics/tasks worked on

3. **Append a review log** to the "Review" section using the <log_format/> below
    - Be specific about outcomes, not activities

4. **Mark habit completed** by appending the current date (in ISO format `YYYY-MM-DD`) as a list item on a new line after the `entries:` field in the yaml frontmatter of `VAULT_ROOT/areas/__metadata/routines/habits/reviews`
</reporting>

<log_format>
### <name>

[1-2 sentence summary of session. use more sentences if particularly important discussions occur]

#### Checklist
[todo task list]
</log_format>