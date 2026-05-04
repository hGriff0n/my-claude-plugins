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

- Walk the file in a single pass, tracking the current heading section (which encodes a default `status` for tasks underneath, see below).
- For each line matching the Obsidian task pattern (`- [ ] …`, `- [x] …`, `- [/] …`, `- [-] …`):
  - `id` ← parsed from a trailing `^<hex>` block-id; if absent, generated and written back via `update_id`.
  - `type` ← `MILESTONE` if the task is under a milestones heading or carries a `#milestone` tag, else `TASK`.
  - `status` ← parsed from the checkbox glyph and from the section heading (`OPEN`, `IN_PROGRESS`, `BLOCKED`, `CLOSED`).
  - `text` ← the line's content with task syntax stripped.
  - `effort` ← derived from the file path: the effort folder name, or `"none"` for the root taskfile.
  - `notes` ← contiguous indented bullet lines following the task.
  - `tags` ← `#tag` tokens parsed from the task line.
  - `dependencies.parent` ← parent task id if this task is nested under another task; `dependencies.children` is filled in a second pass after all tasks are collected.
  - `dependencies.blocked` ← from inline `blocks:<id>` / `blocked-by:<id>` markers in the task line or notes.
  - `time_details` ← `created` / `last_updated` / `due` / `scheduled` from inline metadata when present.

### Write Operations

The parser's `Update` type enumerates:

- `create` — append a new task line to the appropriate taskfile under the section that matches its target status. Generates and writes the block-id back into the file.
- `update_status` — change a task's status. Moves the line between sections in its file when the section encodes status.
- `update_text` — rewrite the task title line, preserving id and metadata.
- `update_dependencies` — rewrite the inline `blocks:` / `blocked-by:` markers and parent nesting.
- `update_metadata` — update `time_details` / `tags` markers on the task line.
- `archive` — move a `CLOSED` task out of the active taskfile into a long-term archive store; the task drops from the index after the next re-parse.
- `update_id` — internal write used by `parse` to backfill a missing block-id; not exposed externally.

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
