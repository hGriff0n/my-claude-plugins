# Move Effort

Implements `specs/arch/routes.md`. Custom method (AIP-136).

## Endpoint

`POST /efforts/{name}/move` — `operation_id: effort_move`

## Request

`MoveEffortRequest`:
- `name: str` (path) — effort directory name.
- `backlog: bool = False`
- `archive: bool = False`

Transition semantics:
| Flags | Meaning | Required current status |
|---|---|---|
| `backlog=true` | Active → Backlog | `ACTIVE` |
| `archive=true` | * → Archive | any |
| both `false` | Backlog → Active | `BACKLOG` |

`backlog=true` and `archive=true` together is invalid.

## Response

`200 OK` — `MoveEffortResponse`:
- `effort: Effort | None` — the updated resource. `None` only when the effort was archived (drops from the index).
- `archived: bool` — `true` only on an archive transition.

A non-archive move returns `{ effort: Effort, archived: false }`. An archive returns `{ effort: null, archived: true }`. The wrapper response (rather than returning `Effort` directly) is needed because the archive case has no resource to return.

`404 Not Found` if no effort matches `name`.
`400 Bad Request` if the requested transition is invalid for the current status, or if any underlying file move fails.

## Behavior

1. Look up the effort via `db.efforts.get(request.name)`; 404 if missing.
2. Call `db.efforts.move(request.name, backlog=…, archive=…)`. The db layer validates the transition (raising `ValueError` on a mismatch — caught and mapped to 400), delegates the file moves to `vault/efforts/parser.move`, and re-syncs the index.
3. Wrap in `MoveEffortResponse` and return.
