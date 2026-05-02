# Route Spec Template

Defines the contract every `src/routes/<system>/<op>/` route must follow. Implementation specs MUST reference this template.

## Files

Each route is a folder under `src/routes/<system>/<op>/` with these required files:

| File | Purpose |
|---|---|
| `route.py` | Handler implementation, FastAPI decorator, pydantic body/response models. |
| `readme.md` | Route spec — Endpoint / Request / Response / Behavior. References this template. |
| `test.py` | Route-level unit tests. |

## `route.py`

- Defines exactly one FastAPI handler.
- Decorator carries the HTTP method, path, status code, and `operation_id` matching the parent folder structure: `<system>_<op>` (e.g. `effort_create`).
- Endpoint-specific request/response wrappers (`<Verb><Resource>Request`, `<Verb><Resource>Response`) live in this file alongside the handler. The resource types they reference are imported from `src/schemas/<system>.py` and never redefined here. If a wrapper needs to be shared across routes within a system, lift it to `routes/<system>/models.py` — never import models across systems.
- Handler reads and writes via `db.<system>` only. Routes MUST NOT call other routes via HTTP. Cross-system orchestration happens by composing `db` calls from multiple systems within a single route handler.
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

## `readme.md`

Each route readme has these sections:

- **Endpoint** — HTTP method, path, `operation_id`.
- **Request** — body schema and/or query/path params; required vs. optional.
- **Response** — success status code and shape; key error responses.
- **Behavior** — what the handler does, including side effects, validation rules, and edge cases.

## Aggregation

`src/routes/server.py` walks all `src/routes/<system>/<op>/route.py` files and registers each handler into a single FastAPI app. The MCP server is generated from this app via `FastMCP.from_fastapi`, so every route is automatically exposed as both a REST endpoint and an MCP tool.
