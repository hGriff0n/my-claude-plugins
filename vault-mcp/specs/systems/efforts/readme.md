# Efforts System

An "effort" is a project folder under `efforts/` in the vault. Each effort owns a `CLAUDE.md`, a `00 README.md`, and a `01 TASKS.md`.

## Resource Schema

Schema: [`schema.yaml`](./schema.yaml) — see `arch/schema.md` for the codegen contract.

`tables: [Effort]`

## File Representation

### Scan

Effort folders are found directly under `efforts/` and `efforts/__backlog/` from the vault root. A folder counts as an effort when it contains all three of: `00 README.md`, `CLAUDE.md`, `01 TASKS.md`. `scan()` returns the matching folder paths.

Folders nested deeper than one level under `efforts/` (e.g. `efforts/<name>/<sub>/`) are not efforts; they may be scratch material owned by an active effort.

### Parse

`parse(folder)` builds a single `Effort`:

- `name` ← final folder component.
- `path` ← vault-relative folder path (`efforts/<name>` or `efforts/__backlog/<name>`).
- `status` ← `BACKLOG` if under `efforts/__backlog/`, else `ACTIVE`.
- `description` ← first non-empty paragraph of `00 README.md` after the title.
- `time_details` ← `created` from folder's earliest mtime; `last_updated` from the most recent mtime among the three required files; `due` / `scheduled` parsed from `00 README.md` frontmatter when present (else null-equivalent dates per yaml contract).
- `display.task_stats.num_by_status` ← counts produced by querying the tasks table for `effort = <name>` grouped by status. The parser populates `0` for each `TaskStatus` value when the tasks table is empty for this effort.

### Write Operations

The parser's `Update` type is an enum of:

- `create` — scaffold a new active effort. Materializes `efforts/<name>/{CLAUDE.md, 00 README.md, 01 TASKS.md}` from templates via `obsidian_cli`. If a placeholder folder already exists at `efforts/<name>/` or `efforts/__ideas/<name>/`, it is moved to `efforts/<name>/<name>/` first so the new templates land alongside existing scratch material.
- `move` — move an effort folder between `efforts/` (status `ACTIVE`), `efforts/__backlog/` (status `BACKLOG`), and archive (deleted from the index). Archive is one-way and removes the folder from the active layout (implementation may move it to a long-term store; the system stops tracking it after archive).

There is no separate write operation per status; `move` is parameterized by the target state.

## Routes

### CreateEffort

Scaffold a new active effort.

#### Endpoint

`POST /efforts` — `operation_id: effort_create`, success `201`.

#### Request

`CreateEffortRequest`:
- `name: str` (required) — used as the effort's directory name.

#### Response

`201 Created` — `Effort`. `display.task_stats.num_by_status` has `0` for every `TaskStatus`.

`400 Bad Request` if:
- An effort with that name already exists (active or backlog).
- Template scaffolding fails (Obsidian CLI error).

#### Behavior

1. Reject with 400 if an effort with `name` is already registered (query the table by name).
2. Invoke the parser's `create` write to scaffold the folder via `obsidian_cli`.
3. After the watcher re-parse settles, return the freshly registered `Effort`.

### GetEffort

Fetch a single effort by name.

#### Endpoint

`GET /efforts/{name}` — `operation_id: effort_get`.

#### Request

`GetEffortRequest`:
- `name: str` (path) — effort directory name.

#### Response

`200 OK` — `Effort`. `display.task_stats.num_by_status` is populated from the live tasks table.

`404 Not Found` if no effort matches `name`.

#### Behavior

1. Query the efforts table for `name`; 404 if missing.
2. Query the tasks table for `effort = <name>` grouped by `status`; populate `display.task_stats.num_by_status`.
3. Return the `Effort`.

### ListEfforts

List efforts, optionally filtered by status.

#### Endpoint

`GET /efforts` — `operation_id: effort_list`.

#### Request

`ListEffortsRequest` (query params):
- `status: EffortStatus | None` — filter by state. Omit for all.
- `include_task_stats: bool = False` — if true, populate `display.task_stats` per entry; otherwise return zeroed stats.
- `page_size: int | None` — reserved for future pagination.
- `page_token: str | None` — reserved for future pagination.

#### Response

`200 OK` — `ListEffortsResponse`:
- `efforts: list[Effort]`.
- `next_page_token: str | None` — currently always `null`.

#### Behavior

1. Query the efforts table with the optional status filter.
2. If `include_task_stats`, batch-query the tasks table grouped by `(effort, status)` and merge counts into each effort's `display.task_stats`.
3. Wrap in `ListEffortsResponse` and return.

### MoveEffort

Move an effort between `ACTIVE`, `BACKLOG`, and archived states. Archive is one-way: an archived effort drops out of the index.

#### Endpoint

`POST /efforts/{name}/move` — `operation_id: effort_move`.

#### Request

`MoveEffortRequest`:
- `name: str` (path) — effort directory name.
- `target: Literal["active", "backlog", "archive"]` (required).

Allowed transitions:

| Current | Target | Effect |
|---|---|---|
| `BACKLOG` | `active` | Move folder out of `efforts/__backlog/`. |
| `ACTIVE` | `backlog` | Move folder into `efforts/__backlog/`. |
| any | `archive` | One-way; effort drops from the index. |

`active`→`active` and `backlog`→`backlog` are no-ops and return the existing effort unchanged.

#### Response

`200 OK` — `MoveEffortResponse`:
- `effort: Effort | null` — the updated resource. `null` only on archive.
- `archived: bool` — `true` only on an archive transition.

`404 Not Found` if no effort matches `name`.
`400 Bad Request` if the underlying file move fails.

#### Behavior

1. Query the efforts table for `name`; 404 if missing.
2. Invoke the parser's `move` write with the target state. The parser handles file moves and registers the change with `vault/debounce`.
3. On archive, the post-watcher re-parse removes the row; respond with `{ effort: null, archived: true }`. Otherwise respond with the refreshed `Effort`.
