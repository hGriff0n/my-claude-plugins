# Efforts System

An "effort" is a project folder under `efforts/` in the vault. Each effort owns a `CLAUDE.md`, a README, and a `01 TASKS.md`.

## States

Efforts have three states, derived from their parent directory:

| State | Path | Meaning |
|---|---|---|
| Active | `efforts/<name>/` | Currently being worked on. |
| Backlog | `efforts/__backlog/<name>/` | On the backburner. |
| Archived | `efforts/__archive/<name>/` | Done — not loaded into the index. |

State is read from the path; there is no in-file status field.

## Discovery

Efforts are discovered by directory scan, not by parsing file content. The scanner walks `efforts/` and `efforts/__backlog/`, treating each immediate child directory as an effort. `__archive/` and `__ideas/` are skipped during normal scanning (`__ideas/` is a placeholder area for unstarted efforts; `__archive/` is intentionally outside the index).

## Lifecycle

- **Create** — scaffold a new active effort. Materializes `efforts/<name>/CLAUDE.md`, `efforts/<name>/00 README.md`, `efforts/<name>/01 TASKS.md` from templates. If a placeholder folder already exists at `efforts/<name>/` or `efforts/__ideas/<name>/`, it is moved into `efforts/<name>/<name>/` first (so the new templates land alongside existing scratch material).
- **Move** — relocate an effort between active and backlog, or archive it. Archive is one-way: an archived effort drops out of the index.

## Architecture

<!-- This is incorrect. This is reflective of the overall arch and not something for the individual system specs -->
Implements `arch/database.md`, `arch/vault.md`, and `arch/routes.md`:

- `src/database/efforts/` — schema and in-memory index. See its `readme.md`.
- `src/vault/efforts/` — directory scan + create/move via `obsidian_cli`. See its `readme.md`.
- `src/routes/efforts/{list,get,create,move}/` — HTTP/MCP surface. See each route's `readme.md`.

## Cross-system relationships

- Tasks reference their owning effort by name (`effort` filter on `db.tasks.list`). Efforts do not reference tasks directly; the tasks system reads effort names from `db.efforts` for filtering.
