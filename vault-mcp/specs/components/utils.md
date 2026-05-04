# Utils Component

Domain-free helpers reused across systems. Anything in `src/utils/` must be importable from any layer (schemas, parsers, database, routes) without creating a cycle.

## Rules

- **No imports from domain modules.** `src/utils/*` may not import from `src/schemas/`, `src/database/`, `src/vault/`, or `src/routes/`.
- **Pure functions or small primitives.** Utils expose primitives, not orchestration. High-level workflows live in the calling layer.
- **Normalize on input.** When a util parses user-supplied text, it should produce a canonical form so downstream code only handles one shape.

## Current modules

| Module | Purpose |
|---|---|
| `utils/dates.py` | Date parsing/formatting helpers. |
| `utils/ids.py` | Generation of internal hex IDs (e.g. task IDs). |
| `utils/formatting.py` | Shared string formatting helpers. |
| `utils/obsidian.py` | Low-level Obsidian-flavored markdown helpers (wikilinks, frontmatter blocks, etc.). Higher-level Obsidian-CLI orchestration lives in `src/vault/obsidian_cli.py`, not here. |

New utils may be added ad hoc as a need arises in two or more systems. A helper used by exactly one system should stay in that system's module until a second caller appears.
