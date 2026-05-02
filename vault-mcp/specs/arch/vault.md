# Vault System Spec Template

Defines the contract every `src/vault/<system>/` module must follow. The `vault/` layer owns the on-disk representation of each system.

## Files

Each vault system is a folder under `src/vault/<name>/` with these required files:

| File | Purpose |
|---|---|
| `parser.py` | Read and write the system's representation in the vault. "Parser" is a logical name — it may parse files (tasks) or scan a directory tree (efforts). |
| `readme.md` | System spec — references this template, describes the parser surface and on-disk layout. |

## `parser.py`

Required surface:

- **Read**
  - `scan(folder=vault_root) -> List[T]` — walks `folder` (defaulting to the vault root) and returns every instance found beneath it. Used by `db.<system>.init` and `db.<system>.refresh`. Directory-based systems (e.g. efforts) implement `scan` by walking the directory tree; file-based systems implement it by discovering and parsing matching files.
  - `read(file) -> List[T]` — file-based systems only. Parses a single file and returns the instances it contains (a tasks file yields many tasks; a system whose file holds a single instance still returns a one-element list for uniformity). Directory-based systems do not implement `read`.
- **Write**
  - `write(element: T)` — persist a single instance.
  - `write(elements: List[T])` — persist a batch. Single- and batch-write are separate entry points so each system can coalesce a batch efficiently (one file rewrite, one debounce registration) instead of looping the single-write path.

  Per-system write helpers (`create_effort`, `move_effort`, etc.) may still exist in `readme.md` when an operation is more than "persist this instance" (e.g. moving an effort between directories). They are layered on top of `write`, not alternatives to it.

`parser.py` imports schema types from `database/<system>/schema.py`. It does **not** import from `db.py` (no upward dependency).

## Shared vault modules

- `vault/debounce.py` — coalesces rapid writes to the same file, holds the self-write registry, and runs the watcher loop. On external file changes (writes not registered as self-writes), it dispatches to the affected system's `db.<system>.refresh()`.
- `vault/obsidian_cli.py` — wraps the Obsidian CLI invocations used to write through Obsidian (so changes are visible to a running Obsidian instance).

## Write paths

Every `write` call lands on disk through one of two backends, chosen per operation by the parser:

- **Through Obsidian** — call `obsidian_cli` for writes that need Obsidian's index to see them immediately (e.g. creating notes from templates). The resulting watcher event causes a (usually idempotent) `db.refresh()`.
- **Direct file I/O** — for high-frequency or batched updates (e.g. task field edits). The write is registered with `vault/debounce` to suppress the watcher echo.

Both backends route through `vault/debounce` so the watcher loop sees a single, consistent self-write registry regardless of which backend was used.

## Variants

A system whose on-disk representation isn't file-based (efforts → directory layout) still implements the same surface (`scan`, write functions); only the parser internals differ. The arch contract is the surface, not the implementation strategy.
