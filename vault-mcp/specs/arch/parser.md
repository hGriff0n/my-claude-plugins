# Parser Spec Template

Defines the contract every `src/vault/<system>/parser.py` module must follow. The vault layer owns the on-disk representation of each system; system specs (e.g. `specs/systems/efforts/readme.md`) describe how their parser implements this contract.

## Files

Each vault system is a folder under `src/vault/<name>/` with these required files:

| File | Purpose |
|---|---|
| `parser.py` | Implements the three-method surface defined below. "Parser" is a logical name — it may parse files (tasks) or walk a directory tree (efforts). |
| `test.py` | Unit tests for the parser. |

The system's spec (Scan / Parse / Write Operations sections) lives under `specs/systems/<name>/readme.md`; there is no per-parser readme.

## Surface

A parser exposes exactly three methods:

- **`scan() -> List[File]`** — walks the vault and returns the set of file/folder units that belong to this system. A `File` may be a folder; deciding what counts as a unit is a per-system choice (a task file, an effort directory, …).
- **`parse(file: File) -> List[T]`** — converts a single scan result into one or more schema instances. The parser is responsible for recursing into folders if the unit is a directory, and for populating the schema types defined in `specs/systems/<name>/schema.yaml`.
- **`write(elem: T, update: Update) -> None`** — applies a write operation to a single schema instance. `Update` is a system-specific type (typically an enum or tagged union) enumerating the supported mutations; each system defines its own in its `### Write Operations` section.

`parser.py` imports schema types from `src/schemas/<name>.py`. It does **not** import from the database (no upward dependency).

## Write paths

Every `write(...)` call lands on disk through one of two backends, chosen per operation by the parser:

- **Through Obsidian** — invoke `vault/obsidian_cli.py` for writes that need Obsidian's index to see them immediately (e.g. creating notes from templates). The resulting watcher event causes a (usually idempotent) re-scan/re-parse.
- **Direct file I/O** — for high-frequency or batched updates (e.g. task field edits). The write is registered with `vault/debounce.py` so the watcher does not echo it back.

Both backends route through `vault/debounce.py` so the watcher loop sees a single, consistent self-write registry regardless of which backend is used.

## Debouncing

Writes to the same target are coalesced by `vault/debounce.py` to avoid hammering disk on rapid successive updates. The debounce window is a parser-internal detail; callers see `write` as fire-and-forget.

## Shared vault modules

- `vault/debounce.py` — coalesces writes, holds the self-write registry, runs the watcher loop, and dispatches external file changes back to the database for re-parse.
- `vault/obsidian_cli.py` — wraps Obsidian CLI invocations for writes that must go through Obsidian.

## Variants

A system whose on-disk representation isn't a single file (efforts → directory layout) still implements the same surface. Only the internals of `scan` / `parse` / `write` differ. The arch contract is the surface, not the implementation strategy.
