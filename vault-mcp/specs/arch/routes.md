# Route Spec Template

Defines the contract every `src/routes/<system>/<op>/` route must follow. Each route's spec lives as a subsection of its system readme (`specs/systems/<name>/readme.md`); see `arch/system.md`.

## Files

Each route is a folder under `src/routes/<system>/<op>/` with these required files:

| File | Purpose |
|---|---|
| `route.py` | Handler implementation, FastAPI decorator, pydantic body/response models. |
| `test.py` | Route-level unit tests. |

## `route.py`

- Defines exactly one FastAPI handler.
- Decorator carries the HTTP method, path, status code, and `operation_id` matching the parent folder structure: `<system>_<op>` (e.g. `effort_create`).
- Endpoint-specific request/response wrappers (`<Verb><Resource>Request`, `<Verb><Resource>Response`) live in this file alongside the handler. The resource types they reference are imported from `src/schemas/<system>.py` and never redefined here.
- Handler reads and writes through the database component (`components/database.md`) and parser writes. Routes MUST NOT call other routes via HTTP. Cross-system orchestration happens by composing queries/writes against multiple registered tables within a single handler.
- Errors are raised as `HTTPException`.

## Request/Response design

Routes follow [Google AIP](https://google.aip.dev/) 131–136 for request/response shapes and resource-oriented URLs. Field names stay repo-native (e.g. `id`, not AIP's `name`); only the structural conventions are adopted.

### Standard methods

| Method | Verb / Path | Request | Response |
|---|---|---|---|
| Get | `GET /<resources>/{id}` | `Get<Resource>Request` | `Resource` |
| List | `GET /<resources>` | `List<Resource>Request` | `List<Resource>Response` |
| Create | `POST /<resources>` | `Create<Resource>Request` | `Resource` |
| Update | `PATCH /<resources>/{id}` | `Update<Resource>Request` | `Resource` |
| Delete | `DELETE /<resources>/{id}` | `Delete<Resource>Request` | 204 / empty |

### Custom methods

Non-CRUD operations (e.g. moving an effort) follow AIP-136 for typing but use a slash separator instead of `:` for the verb: `POST /<resources>/{id}/<verb>`, request type `<Verb><Resource>Request`. The response is a typed `<Verb><Resource>Response` unless the natural result is the resource itself, in which case return `Resource` directly.

### Request types

- Every route has a typed pydantic request model, even when the HTTP body is empty. Path and query params are fields on this model. This keeps the MCP tool surface uniform and self-describing.
- Path `id` is a field on the request model (FastAPI binds it from the path).

### Response types

- Get / Create / Update return the resource type imported from `schemas/<system>.py`.
- List returns `List<Resource>Response` with two fields: `<resource_plural>: list[Resource]` and `next_page_token: str | None`.
- Delete returns 204 with no body.
- Custom methods follow the rule above.

## Spec sections (in the system readme)

Each route subsection inside the owning system readme uses these headings:

- **Endpoint** — HTTP method, path, `operation_id`.
- **Request** — body schema and/or query/path params; required vs. optional.
- **Response** — success status code and shape; key error responses.
- **Behavior** — what the handler does, including side effects, validation rules, and edge cases.

## Aggregation

Each `route.py` defines its own `router = APIRouter()` and attaches its handler to it. `src/routes/routes.py` imports every `<system>/<op>/route.py` module and includes each `router` into a single top-level `APIRouter`, exported as `router`. The server mounts this joined router onto the FastAPI app, and the MCP server is generated from that app via `FastMCP.from_fastapi`, so every route is automatically exposed as both a REST endpoint and an MCP tool.

When a new route is added, its module must be imported and included in `src/routes/routes.py`.
