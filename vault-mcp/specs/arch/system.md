# System Spec Template

Defines the contract every `specs/systems/<name>/readme.md` must follow. A system is the unit that ties together a domain (efforts, tasks, …) across the parser, schema, database, and route layers.

## Layout

Each system lives under `specs/systems/<name>/` with:

| File | Purpose |
|---|---|
| `readme.md` | The system spec — sections defined below. References this template. |
| `schema.yaml` | OpenAPI document describing the system's domain types. Source of truth for `src/schemas/<name>.py`. See `arch/schema.md`. |

## Required sections

A system readme contains exactly these top-level sections, in this order. Each section is interpreted by reference to a sibling arch file.

### `## Resource Schema`

- One-line pointer to the sibling `schema.yaml`.
- `tables: [<TypeA>, <TypeB>, …]` — explicit list of OpenAPI types from `schema.yaml` that the system registers as database tables (via `components/database.md`'s `register`). Types not listed here are nested/value types only.

See `arch/schema.md` for what belongs in the yaml and what does not.

### `## File Representation`

Describes how the system maps onto the vault. Three subsections, matching the three-method parser surface in `arch/parser.md`:

- `### Scan` — what the parser's `scan()` returns for this system (which files/folders count as a unit).
- `### Parse` — how `parse(file)` converts a scan result into one or more schema instances.
- `### Write Operations` — the named write operations the parser supports, each one mapping to a `write(elem, update)` call.

### `## Routes`

One subsection per route, named after the route's operation (e.g. `### CreateEffort`). Each route subsection contains:

- One-line summary.
- `#### Endpoint` — HTTP method, path, `operation_id`, success status.
- `#### Request` — request model name and fields.
- `#### Response` — success response shape; key error responses.
- `#### Behavior` — what the handler does, including side effects and validation.

The format is fixed by `arch/routes.md`; this section is the authoritative spec for the routes (the `src/routes/<system>/<op>/` folder no longer carries a readme).

## Cross-system references

Systems may reference another system's tables through the database's generic `query`/`update` surface. There is no per-system db module; cross-system access is a natural consequence of every registered table being queryable. Mutations to a foreign system's data must still go through that system's documented write operations / routes — do not write to another system's table directly.
