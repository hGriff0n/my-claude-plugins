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
  - `dependencies.blocked` ← parsed from the `blocked` tag (canonical glyph `⛔`, also accepted as `#blocked:<id>` or `[blocked::<id>]`). Multiple blockers are encoded as a comma-separated value.
  - `time_details` ← `created` / `due` / `scheduled` / `completed` from the corresponding emoji/dataview/hashtag entries when present.

### Write Operations

The parser's `Update` type enumerates:

- `create` — append a new task line to the appropriate taskfile. Generates an `id` tag and renders the task in canonical form via `utils/formatting.render_tags`.
- `update_status` — change a task's status by rewriting the checkbox glyph in place.
- `update_text` — rewrite the task title portion of the line, preserving the trailing tag block.
- `update_dependencies` — rewrite the `blocked` tag (and any parent-nesting indent) for the task. There are no separate `blocks:` / `blocked-by:` markers — outgoing-blocker information is reconstructed by the indexer from the `blocked` values of other tasks.
- `update_metadata` — update individual tag entries (`due`, `scheduled`, `created`, `completed`, arbitrary `#tag` / dataview entries). All tags are re-rendered through the canonical formatter so the on-disk syntax converges to the canonical form for known tags.
- `archive` — move a `CLOSED` task out of the active taskfile into a long-term archive store; the task drops from the index after the next re-parse.
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

### ArchiveTask

Archive a closed task. One-way: the task drops from the index.

#### Endpoint

`POST /tasks/{id}/archive` — `operation_id: task_archive`.

#### Request

`ArchiveTaskRequest`:
- `id: str` (path).

#### Response

`200 OK` — `ArchiveTaskResponse`:
- `archived: bool` — always `true` on success.

`404 Not Found` if no task matches `id`.
`400 Bad Request` if the task is not in `CLOSED` status.

#### Behavior

1. Load the task by `id`; 404 if missing. 400 if `status != CLOSED`.
2. Invoke the parser's `archive` write.
3. After re-parse, the task is no longer in the table; return `{ archived: true }`.
