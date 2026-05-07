# Tasks System

A "task" is a checklist line in an Obsidian taskfile. Tasks live in two places: per-effort task files (`efforts/<name>/01 TASKS.md` and the same file under `efforts/__backlog/<name>/`) and the root taskfile (vault root `01 TASKS.md`) for tasks not attached to an effort.

## Resource Schema

Schema: [`schema.yaml`](./schema.yaml) — see `arch/schema.md` for the codegen contract.

`tables: [Task]`

## File Representation

### Scan

`scan()` returns the set of taskfiles in the vault:

- The root `01 TASKS.md` if it exists.
- `efforts/<name>/01 TASKS.md` for every effort folder.
- `efforts/__backlog/<name>/01 TASKS.md` for every backlogged effort.

A taskfile is the unit of scan; individual tasks are extracted by `parse`.

### Parse

`parse(file)` reads a taskfile and returns a `list[Task]`. Per file:

- Optionally consume a leading YAML frontmatter block (`---` … `---`) and preserve it verbatim for write-back.
- Walk the body in a single pass, tracking the current heading section. Headings delimit sections and are preserved on each task for write-back, but they do **not** encode `status`.
- For each line matching the Obsidian task pattern (`- [ ] …`, `- [x] …`, `- [/] …`, `- [-] …`) — `- [[…]]` wiki-link lines are excluded:
  - The line's content (everything after `- [x] `) is split into a `title` and a trailing metadata tail. The split point is the first occurrence of any of:
    - a known emoji from the canonical map (🆔 `id`, 📅 `due`, ⏳ `scheduled`, ➕ `created`, ✅ `completed`, ⛔ `blocked`),
    - a `#tag` token at a word boundary that is not inside `[[…]]` or `(…)`,
    - a dataview property opener `[key::` or `(key::`.
  - The metadata tail is tokenised into `tags: dict[str, str]` plus a `dataview_tags: set[str]` recording which tag names were declared with dataview syntax. Three syntaxes are recognised:
    - **Emoji**: known emoji → next whitespace token is the value (`📅 2026-02-15` → `due=2026-02-15`). Unknown emoji greedily consume tokens until the next metadata token.
    - **Hashtag**: `#name` → flag tag with empty value; `#name:value` → tag with value.
    - **Dataview**: `[name::value]` or `(name::value)` → tag with value, name added to `dataview_tags`. Tags `estimate`, `actual`, `effort` are always re-rendered as dataview on write regardless of original syntax.
  - `id` ← `tags["id"]` if present (any of the three syntaxes); if absent, generated and written back via `update_id`.
  - `type` ← `MILESTONE` if the line is an L4 heading (`#### …`), or — for back-compat — if the task is under a milestones heading or carries a `milestone` tag; else `TASK`.

  In addition to `- [ ]` task lines, the parser also recognises:

  - **Milestone headings (`#### text`)**: parsed as a MILESTONE-type task. The line's metadata tail (everything after the heading text) is parsed with the same emoji/hashtag/dataview tokeniser used for task lines. Missing `id` tags are generated and written back. A milestone heading is the parent of every subsequent unindented `- [ ]` task until the next heading (of any level) or end of file. Nested children continue to parent on their enclosing task. On write, MILESTONE tasks are always projected as `#### text <tags>` lines, never as `- [ ]` with a `#milestone` tag.
  - **TASKFILE wrapper (ephemeral)**: at write time the parser builds an in-memory TASKFILE-typed task whose `notes` are the file's frontmatter lines (one note per non-empty line) and whose `children` are the parentless tasks in the file. The wrapper is not persisted to the database; it exists only to drive a uniform recursive emit of the file body.
  - `status` ← from the checkbox glyph alone: `[ ]` → `OPEN`, `[x]` → `CLOSED`, `[/]` → `IN_PROGRESS`, `[-]` → cancelled. `BLOCKED` is derived at the API mapping layer when a `blocked` tag with a non-empty value is present.
  - `text` ← the title portion (task line with checkbox prefix and metadata tail stripped).
  - `effort` ← derived from the file path: the effort folder name, or `"none"` for the root taskfile.
  - `notes` ← contiguous indented bullet lines following the task line whose indent exceeds the task's indent. Stored with their relative indent so nested note structure round-trips.
  - `dependencies.parent` ← the id of the enclosing task when this task is a more-deeply-indented `- [ ]` line under another task; `dependencies.children` is filled in a second pass after all tasks are collected.
  - `dependencies.blocked` ← parsed from the `blocked` tag (canonical glyph `⛔`, also accepted as `#blocked:<id>` or `[blocked::<id>]`). Multiple blockers are encoded as a comma-separated value. After all taskfiles have been indexed (initial scan and on every subsequent re-parse triggered by the watcher), an integrity pass prunes any `blocked` entry that references an id no longer present in the tasks table; the corresponding `blocked` tag is rewritten on disk via `update_dependencies`. The same pass is what reconciles parent/child links after a task disappears — a now-orphaned `dependencies.parent` reference is dropped, and the missing id is removed from any other task's `dependencies.children`.
  - `time_details` ← `created` / `due` / `scheduled` / `completed` from the corresponding emoji/dataview/hashtag entries when present.

### Write Operations

The parser's `Update` type enumerates:

- `create` — append a new task line to the appropriate taskfile. Generates an `id` tag and renders the task in canonical form via `utils/formatting.render_tags`.
- `update_status` — change a task's status by rewriting the checkbox glyph in place.
- `update_text` — rewrite the task title portion of the line, preserving the trailing tag block.
- `update_dependencies` — rewrite the `blocked` tag (and any parent-nesting indent) for the task. There are no separate `blocks:` / `blocked-by:` markers — outgoing-blocker information is reconstructed by the indexer from the `blocked` values of other tasks.
- `update_metadata` — update individual tag entries (`due`, `scheduled`, `created`, `completed`, arbitrary `#tag` / dataview entries). All tags are re-rendered through the canonical formatter so the on-disk syntax converges to the canonical form for known tags.
- `archive` — move a `CLOSED` task out of its source taskfile and append it to the daily note for its `completed` date. The task drops from the index after the next re-parse.
- `update_id` — internal write used by `parse` to backfill a missing `id` tag; not exposed externally.

All writes are direct file I/O batched through `vault/debounce.py` (see `arch/parser.md`).

## Routes

### CreateTask

Create a new task in the root taskfile or under an effort.

#### Endpoint

`POST /tasks` — `operation_id: task_create`, success `201`.

#### Request

`CreateTaskRequest`:
- `text: str` (required) — task title.
- `effort: str = "none"` — owning effort name; `"none"` targets the root taskfile.
- `status: TaskStatus = OPEN`.
- `type: TaskType = TASK`.
- `parent: str | None` — parent task id for nesting.

#### Response

`201 Created` — `Task`.

`400 Bad Request` if `effort` is not `"none"` and no matching effort exists, or if `parent` is set and the parent id is unknown.

#### Behavior

1. Resolve the target taskfile from `effort`. 400 if the effort is unknown.
2. Invoke the parser's `create` write; the parser generates the id, writes the line, and registers the write with debounce.
3. After re-parse, return the newly inserted `Task`.

### GetTask

Fetch a task by id.

#### Endpoint

`GET /tasks/{id}` — `operation_id: task_get`.

#### Request

`GetTaskRequest`:
- `id: str` (path).

#### Response

`200 OK` — `Task`.
`404 Not Found` if no task matches `id`.

#### Behavior

1. Query the tasks table by `id`; 404 if missing.
2. Return the `Task`.

### ListTasks

List tasks with optional filters.

#### Endpoint

`GET /tasks` — `operation_id: task_list`.

#### Request

`ListTasksRequest` (query params):
- `effort: str | None` — filter by owning effort (`"none"` for root taskfile).
- `status: TaskStatus | None`.
- `type: TaskType | None`.
- `tag: str | None` — filter to tasks carrying this tag.
- `page_size: int | None` — reserved.
- `page_token: str | None` — reserved.

#### Response

`200 OK` — `ListTasksResponse`:
- `tasks: list[Task]`.
- `next_page_token: str | None` — currently always `null`.

#### Behavior

1. Build the SQL query against the tasks table from the supplied filters.
2. Run it via `database.query(...)` and return.

### UpdateTask

Update a task's mutable fields.

#### Endpoint

`PATCH /tasks/{id}` — `operation_id: task_update`.

#### Request

`UpdateTaskRequest`:
- `id: str` (path).
- `text: str | None`.
- `status: TaskStatus | None`.
- `tags: list[str] | None` — replaces the full tag set when provided.
- `dependencies: Dependencies | None` — replaces dependency block when provided.
- `time_details: TimeBlock | None` — partial updates allowed via field-level nulls in a future revision; current contract replaces the block.

#### Response

`200 OK` — `Task`.
`404 Not Found` if no task matches `id`.
`400 Bad Request` on invalid status transition or unknown referenced task ids in `dependencies`.

#### Behavior

1. Load the task by `id`; 404 if missing.
2. For each populated field, invoke the corresponding parser write (`update_text`, `update_status`, `update_metadata`, `update_dependencies`).
3. After re-parse, return the refreshed `Task`.

### ArchiveTasks

Archive `CLOSED` tasks by moving them out of their source taskfiles and appending them to the daily note for the date each task was completed. One-way: archived tasks drop from the index.

The default (no filters) archives every `CLOSED` task in the database. Filters narrow the set; an explicit `ids` list bypasses status/effort filters and archives exactly those tasks (still requiring each to be `CLOSED`).

#### Endpoint

`POST /tasks/archive` — `operation_id: task_archive`.

#### Request

`ArchiveTasksRequest`:
- `ids: list[str] | None` — explicit task ids to archive. When omitted, every `CLOSED` task in the database is selected (subject to `effort`).
- `effort: str | None` — restrict the default selection to a single effort (`"none"` for the root taskfile). Ignored when `ids` is provided.
- `dry_run: bool = false` — compute the selection and grouping but do not write to daily notes or source files.

#### Response

`200 OK` — `ArchiveTasksResponse`:
- `archived: dict[str, int]` — map of daily-note files written to and the number of tasks archived to file
- `failures: list[str]` — completion dates whose daily-note write failed; the corresponding tasks remain in their source files.
- `updates: list[{id, OPENED | CLOSED}]` - list of tasks that were modified during the archival, paired with an "OPENED"/"CLOSED" enum depending on whether the task was re-opened (because it had open children - integrity fix; see Behavior) or closed (ie. archived)
- `dry_run: bool` — echoes the request flag.

`400 Bad Request` if any explicit `id` is unknown or refers to a non-`CLOSED` task.

#### Behavior

Modeled on `src/scripts/archive_tasks.py`.

1. **Select**: if `ids` is provided, load those tasks (400 on unknown id or non-`CLOSED` status). Otherwise query all `CLOSED` tasks, optionally filtered by `effort`.
2. **Integrity pass**: walk the task tree of the selection. Any `CLOSED` task that has open descendants is reopened (status flipped back to `OPEN`, with `blocked` populated from the open children's ids) and excluded from this archive run; its done descendants remain individually archivable. Reopened ids are returned in the response.
3. **Group by completion date**: every remaining selected task must carry a `completed` tag. Group tasks by that date.
4. **Per-date write**:
   - Resolve the daily-note path under `areas/journal/<YYYY>/<MM Month>/<DD>.md`.
   - Render the date's tasks via the parser's canonical task serializer. A task is nested under its parent only if that parent is also being archived on the same date; otherwise it renders at indent 0.
   - Append a `## Completed Tasks` section with the rendered content. If the daily note does not yet exist, create it from the daily-note template.
   - Only if the daily-note write succeeds, invoke the parser's `archive` write for each task in that date group, removing them from their source files. A failure on one date does not block other dates; the failed date is recorded in `failures`.