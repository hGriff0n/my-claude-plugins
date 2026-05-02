# Efforts Vault Parser

Implements `specs/arch/vault.md` for the efforts system. The "parser" is a directory scanner — efforts have no on-disk file format to parse beyond their folder layout.

## On-disk layout

```
efforts/
  <name>/                    active
    CLAUDE.md
    00 README.md
    01 TASKS.md
  __backlog/<name>/          backlog
  __archive/<name>/          archived (not indexed)
  __ideas/<name>/            placeholder, claimed on create
```

## `parser.py` surface

- `scan(vault_root: Path) -> list[Effort]` — walks `efforts/` and `efforts/__backlog/`, builds `Effort` instances. Skips `__archive/` and `__ideas/`. Sets `tasks_file` to the effort's `01 TASKS.md` if present.
- `create(name: str, vault_root: Path) -> None` — materializes the three template files via `obsidian_cli`:
  - `efforts/<name>/CLAUDE.md` from template `efforts/claude`
  - `efforts/<name>/00 README.md` from template `efforts/readme`
  - `efforts/<name>/01 TASKS.md` from template `efforts/taskfile`
  Before scaffolding, if `efforts/<name>/` or `efforts/__ideas/<name>/` already exists, it is moved into `efforts/<name>/<name>/` so its contents are preserved.
- `move(name: str, vault_root: Path, *, backlog: bool, archive: bool) -> None` — relocates the effort folder. Iterative DFS: Obsidian's `move` operates on files (not folders), so every leaf file is moved individually with its relative subpath preserved under the destination.

## Write strategy

All writes go through `obsidian_cli`. The debounce / self-write registry is not used by the efforts parser — Obsidian-mediated writes echo through the watcher and trigger an idempotent `db.efforts.refresh()`, which is acceptable at the rate efforts are mutated.
