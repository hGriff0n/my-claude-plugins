# List Efforts

Implements `specs/arch/routes.md`.

## Endpoint

`GET /efforts` — `operation_id: effort_list`

## Request

`ListEffortsRequest` (query params):
- `status: EffortStatus | None` — filter by state. Omit for all.
- `include_task_counts: bool = False` — if true, populate `task_count` on each returned `Effort`.
- `page_size: int | None` — reserved for future pagination; current implementation returns all matches.
- `page_token: str | None` — reserved for future pagination.

## Response

`200 OK` — `ListEffortsResponse`:
- `efforts: list[Effort]` — resource type from `schemas/efforts.py`. `task_count` (count of non-done tasks) is populated on each entry only when `include_task_counts=true`; otherwise `None`.
- `next_page_token: str | None` — currently always `None`.

## Behavior

1. `efforts = db.efforts.list(status=request.status)`.
2. If `include_task_counts`, for each effort with a `tasks_file`, query `db.tasks.list(effort=effort.name, status="open,in-progress")` and set `effort.task_count` to its length. Efforts without a `tasks_file` get `task_count = 0`.
3. Wrap in `ListEffortsResponse` and return.
