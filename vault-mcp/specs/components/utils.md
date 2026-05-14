# Utils Component

Domain-free helpers reused across systems. Anything in `src/utils/` must be importable from any layer (schemas, parsers, database, routes) without creating a cycle.

## Rules

- **No imports from domain modules.** `src/utils/*` may not import from `src/schemas/`, `src/database/`, `src/vault/`, or `src/routes/`.
- **Pure functions or small primitives.** Utils expose primitives, not orchestration. High-level workflows live in the calling layer.
- **Normalize on input.** When a util parses user-supplied text, it should produce a canonical form so downstream code only handles one shape.

New utils may be added ad hoc as a need arises in two or more systems. A helper used by exactly one system should stay in that system's module until a second caller appears.

## dates.py

Date and duration parsing primitives. Pure functions, no external dependencies.

### `parse_date(date_str: str) -> Optional[str]`

Parses a date expression into canonical ISO 8601 (`YYYY-MM-DD`).

Accepted shapes:
- ISO 8601 (`2026-02-15`)
- Natural language (`today`, `tomorrow`, weekday names, `next <weekday>`)
- Relative (`in 3 days`, `in 2 weeks`)
- Prose prefixes that are stripped before parsing (`before `, `by `, `due `, `on `)
- Urgency synonyms resolved to today (`asap`, `immediately`, `urgent`, `now`)
- Month/day forms (`%B %d`, `%b %d`, `%m/%d`, `%m-%d`, with optional year)

Bare weekdays resolve to the next occurrence; `next <weekday>` always skips the current week. Month/day forms without a year resolve to the current year, rolling forward to next year if already past. Returns `None` if no shape matches.

### `duration_to_minutes(duration_str: str) -> Optional[int]`

Parses a duration expression into total minutes. Recognizes day, hour, and minute components in either short (`d`/`h`/`m`) or long (`days`/`hours`/`minutes`) form, including fractional days/hours and combined forms (`2h30m`, `2.5h`, `2 hours 30 minutes`). Returns `None` if no recognized component is found.

### `minutes_to_duration(total_minutes: int) -> Optional[str]`

Formats a minute count as the canonical compact form (`<d>d<h>h<m>m`), omitting any zero components. Returns `None` for zero or falsy input.

### `parse_duration(duration_str: str) -> Optional[str]`

Normalizes any accepted duration expression into the canonical compact form. Composition of `duration_to_minutes` then `minutes_to_duration`. Returns `None` if the input cannot be parsed.

## ids.py

Internal hex ID generation.

### `generate_task_id(length: int = 6) -> str`

Returns a cryptographically random lowercase hex string of the requested character length. Used wherever the system needs an opaque identifier (e.g. task IDs); collision handling is the caller's responsibility.

## formatting.py

Canonical rendering of task tags back to markdown. Single source of truth for how each tag shape (emoji, dataview property, hashtag) is serialized — changing a mapping here and re-normalizing the vault updates every task file.

Module constants:
- `TAG_TO_EMOJI` — name → emoji mapping for Obsidian Tasks plugin compatible tags (`id`, `due`, `scheduled`, `created`, `completed`, `blocked`).
- `EMOJI_TO_TAG` — inverse of the above, for parsers.
- `TAG_FORCE_DATAVIEW` — tag names always rendered as dataview properties regardless of how they were originally written (`estimate`, `actual`, `effort`).

### `render_tag(name: str, value: str, is_dataview: bool = False) -> str`

Renders a single tag in its canonical form. Resolution order:
1. Known emoji tag (`name` in `TAG_TO_EMOJI`) → `<emoji> <value>`.
2. `name` is itself an emoji character → `<emoji> <value>`, or just `<emoji>` if value is empty.
3. Forced dataview tag or `is_dataview=True` → `[<name>:: <value>]`, or `[<name>::]` if value is empty.
4. Otherwise hashtag → `#<name>:<value>`, or `#<name>` if value is empty.

### `render_tags(tags: Dict[str, str], dataview_tags: Set[str] = frozenset()) -> str`

Renders a mapping of tags as a single space-separated string in iteration order, dispatching each entry through `render_tag`. `dataview_tags` flags which names should be forced through the dataview branch. Returns an empty string if `tags` is empty.

## obsidian.py

Low-level helpers for talking to the Obsidian CLI. Higher-level orchestration (multi-step write flows, retries, vault-aware logic) lives in `src/vault/obsidian_cli.py`, not here.

Module constants:
- `OBSIDIAN_EXE` — absolute path to the Obsidian CLI executable.
- `CONTENT_CHUNK_BYTES` — conservative chunk size (2000) for the CLI's `content` argument. Obsidian's main process reads each pipe chunk as a complete JSON message; payloads larger than this can crash the IPC parser or fail silently with `rc=0` and empty stdout. Callers passing large content must split with `split_on_line_boundaries` first.

### `obsidian_cli(*args: str) -> subprocess.CompletedProcess`

Invokes the Obsidian CLI with the given args and returns the completed process. Mockable in tests. Beyond running the subprocess, this helper rewrites the result to surface two failure modes the CLI does not signal via exit code:

- If `rc=0` but stdout begins with `Error:`, the result is rewritten to `rc=1` with stderr set to the stdout body.
- If `rc=0` and the command is in the success-marker set (currently `append` → `"Appended to"`, `create` → `"Created:"`) but the marker is missing from stdout, the result is rewritten to `rc=1` with stderr describing the silent-failure case.

Console windows are suppressed on Windows.

### `split_on_line_boundaries(content: str, max_bytes: int) -> List[str]`

Splits `content` into chunks no larger than `max_bytes` (UTF-8 encoded), breaking only at newline boundaries. Used to keep CLI `content` payloads under `CONTENT_CHUNK_BYTES`. A single line longer than `max_bytes` is emitted as its own (oversized) chunk rather than being split mid-line.
