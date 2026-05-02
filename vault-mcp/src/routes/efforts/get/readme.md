# Get Effort

Implements `specs/arch/routes.md`.

## Endpoint

`GET /efforts/{name}` — `operation_id: effort_get`

## Request

`GetEffortRequest`:
- `name: str` (path) — effort directory name.

## Response

`200 OK` — `Effort` from `schemas/efforts.py`. When `tasks_file` is set, the per-status count fields (`tasks_open`, `tasks_in_progress`, `tasks_done`) on the model are populated; otherwise they are `None`.

`404 Not Found` if no effort matches `name`.

## Behavior

1. `effort = db.efforts.get(request.name)`; 404 if `None`.
2. If `effort.tasks_file` is set, run three `db.tasks.list(effort=name, status=<each>)` queries and set `tasks_open`, `tasks_in_progress`, `tasks_done` on the returned model.
3. Return the `Effort`.
