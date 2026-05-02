# Create Effort

Implements `specs/arch/routes.md`.

## Endpoint

`POST /efforts` — `operation_id: effort_create`, success `201`.

## Request

`CreateEffortRequest`:
- `name: str` (required) — used as the effort's directory name.

## Response

`201 Created` — `Effort` from `schemas/efforts.py`. Per-status task count fields are `None` (a freshly created effort has no tasks).

`400 Bad Request` if:
- An effort with that name already exists.
- Template scaffolding fails (Obsidian CLI error).

## Behavior

1. Reject with 400 if `db.efforts.get(request.name)` is non-null.
2. Call `db.efforts.create(request.name)`. The db layer delegates scaffolding to `vault/efforts/parser.create` and re-syncs its index entry.
3. Return the new `Effort`.
