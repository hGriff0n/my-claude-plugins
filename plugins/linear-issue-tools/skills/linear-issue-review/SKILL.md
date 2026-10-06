---
name: linear-issue-review
description: Review a Linear issue's readiness for Cyrus and refine a rewrite with the user. Use when asked to review, audit, or improve a Linear issue, whether one is ready for Cyrus, or why Cyrus would get stuck on one.
argument-hint: analyze <ISSUE-ID|path-to-draft.md>
---

# Linear issue review (pre-Cyrus)

Rubric source: https://www.atcyrus.com/docs/writing-great-issues. Re-fetch it each run; if it cannot be fetched, say so and use the criteria below.

## Modes

- **analyze** `<ISSUE-ID>` or `<path-to-draft.md>`: the entrypoint. Gather context, write the draft, and reply with the report. Read-only in Linear. Then continue straight into discuss with the user, in the same conversation.
- **discuss**: how the conversation continues after analyze, in the same conversation, working from the draft already in context. If asked to discuss an issue with no prior analyze in this conversation, run analyze first.
- **commit**: an explicit follow-up step only triggered by user-typed commands, never automatically. Writing to Linear is done only by the separate user-typed command `/linear-issue-commit <ISSUE-ID>` (see `commands/linear-issue-commit.md` in this plugin). This skill never writes to Linear.

If the request names more than one issue, see **Multiple issues** below before doing anything else.

**Draft-path input:** analyze can be pointed at an existing `draft.md` instead of an `<ISSUE-ID>`, e.g. to resume review of a draft edited outside the conversation. Read the `issue:` field from its YAML frontmatter and use that ID to pull live Linear context (project, labels, relations, docs — whatever isn't in the draft itself); treat the draft's body as the candidate text instead of the issue's current live description. This is why every `draft.md` must carry `issue: <ISSUE-ID>` in its frontmatter, even though it's redundant with the folder name.

Working folder (temporary): `./issue-reviews/<ISSUE-ID>/` containing `draft.md` (proposed description, with YAML frontmatter `issue: <ISSUE-ID>`) and `base.json` (the issue as read: description, `updatedAt`). It exists so a draft can be pointed at directly, and so `/linear-issue-commit` has something to read later. The commit command deletes it after a successful write. The report is never written to a file.

## Environment config

Cyrus's environment differs from the reviewer's machine, so judge feasibility against inferred config, not against what is installed locally.

1. **`[repo=<repo>]` tag**: if the issue text has one, use `<repo>` as the inferred repository and skip the project-link lookup below.
2. **`[model=<model>]` tag**: if the issue text has one, assume Cyrus is running that model's capabilities for this issue instead of the default (Sonnet) throughout the analysis, including "Model and effort" — but still recommend a different model if the tagged one is insufficient or overkill.
3. Otherwise, find the routing repo from the project: fetch the issue's project (its resources) and look for a link resource to `github.com/<owner>/<repo>`. The `<repo>` path segment is the Cyrus routing label. If no such link exists on the project, and none at workspace/initiative level either, the project is not integrated with Cyrus: give that as the Repo reason in the scorecard and review the issue text only, without assuming any repos, tools, or labels.
4. **Cross-project mismatch**: the issue may need work outside the repo the main link implies (a new cross-cutting system, or work that actually belongs in a sibling repo). Comparing the issue text against the linked repo's README is unreliable for genuinely new features, so don't use it to silently re-route — surface a mismatch as a clarification question instead. If the project has additional numbered link resources (e.g. "Github 2", "Github 3"), treat those as fallback repos worth naming in that question when the primary repo doesn't plausibly fit; do not guess which one is right.
5. Once a repo is identified, fetch `.mcp.json`, `.claude/settings.json`, and the `.claude/skills/` listing from its root (if present) for the tools, skills, plugins, and MCP servers actually available there, then read `docs/glossary.md` (project terms, including what tool names like "Unity MCP" refer to) and `docs/building.md` if they exist; its "Cyrus environment" section may declare additional tools, licenses, and constraints. If none of these exist, don't assume any repo-specific tools beyond Cyrus's defaults.
6. **Testing rules**: only if the issue's validation approach depends on how tests are run, read `docs/testing.md` from the repo root. If neither it nor the issue says how, raise it as a clarification question rather than guessing a command.
7. **Work approach labels**: fetch https://www.atcyrus.com/docs/labels-and-routing each run for the current table (Debugger: `Bug`, `Hotfix`; Builder: `Feature`, `Improvement`; Orchestrator: `Orchestrator`, `Epic`; Stacked PRs: `Graphite` + `Orchestrator`). Model labels (`Fable`, `Opus`, `Sonnet`, `Haiku`) are defined there too; a `[model=...]` tag overrides them when present. Effort is not something Cyrus reads from an issue — it has no label or tag form — so it is only ever this skill's own recommendation, never rendered as a tag.

**Reading repo files:** read files from the routing repo (`.mcp.json`, `.claude/settings.json`, README, docs) with `gh api repos/<owner>/<repo>/contents/<path> -H "Accept: application/vnd.github.raw"`. Fall back to WebFetch or raw URLs only if `gh` is not installed or not authenticated. A 404 from WebFetch on a private repo does not mean the file is missing.

**Declared tooling is available:** treat everything declared in `.mcp.json`, `.claude/settings.json` (including its `enabledPlugins`), `.claude/skills/`, or the `docs/building.md` Cyrus-environment section as fully usable by Cyrus. Do not try to verify access to it, and do not raise access failures about it; this review is a quick validation pass, not an environment audit. Do read what it can do, though (step 3a). If these files are silent on something the issue depends on, ask it as a normal clarification question.

Repo names come only from a `[repo=...]` tag or the project's Github link (and its numbered fallbacks). Names that appear in the issue text are the author's claims: quote them as such, and do not read ordinary words (e.g. "assets", "game") as repo names.

Do not hard-code repo, branch, or engine/package versions in issues when the repo can answer them; check whether Cyrus can read them itself (e.g. `ProjectSettings/ProjectVersion.txt`, `Packages/manifest.json`).

## Analyze

### 1. Gather context (read-only)
Issue, comments, sub-issues, parent, siblings, blocking/blocked-by and related relations, project and milestone descriptions, and documents. Read siblings and relations together with the issue: a problem is often only visible across issues. Note that files embedded in a description have signed URLs that expire in about five minutes and do not appear under `attachments`; download and read them immediately.

### 2. Score against the Cyrus guide
Rate each criterion Met / Partial / Missing: title, context, objective, acceptance criteria (verifiable and self-checkable), validation approach, output format, process notes, references, routing (repo, labels, work approach), dependencies. Flag unfilled template placeholders (`<...>`) and empty sections automatically. Give an overall score out of 10. The per-criterion ratings are working notes, not report content: each gap should surface as a clarification question, wrong direction, or contradiction it would cause, and gaps that cause none of these (e.g. a vague title, empty References) go to Suggested changes.

Check the work approach label against the issue's actual shape (bug fix vs fully-scoped feature vs work needing sub-issue breakdown vs a stacked-PR chain), using the table from the labels-and-routing doc. Most issues today carry only `Bug`/`Task`-style labels regardless of shape, so expect this to mismatch often; when it does, propose the correct label(s) in Suggested changes rather than treating it as a blocker.

### 3. Search for problems
- **Clarification:** the specific questions Cyrus would post, in its likely order.
- **Wrong direction:** misinterpretations, scope creep into sibling issues, wrong API or version, guessing at unspecified choices, claiming done without verification, edits that break tooling (e.g. missing metadata files, hand-edited generated files), and labels that mislead.
  - **Verification built into the product:** a criterion phrased as something to build ("a command that verifies the uploaded data matches") when the intent is evidence in the PR. Cyrus will ship it as a feature and design around it (checksum columns, self-test modes, row-matching keys). Reword it so it can be met with what the issue already ships plus standard tools, with the results reported in the PR.
  - **Reports written into docs:** a doc criterion that asks for a "report", findings, or everything to record. Cyrus will put measurements, history, and design rationale into `docs/`. Doc criteria should name the file and what a reader must be able to do with it (run it, query it, extend it); findings go in the PR.
- **Blocked or contradictory:** unresolved blockers on a queued issue; text implying a dependency that the relations do not show (and the reverse); statements that conflict with comments or the parent.
- **Iterations and quota:** expected rounds as written and after the suggested changes. The user is on a subscription plan, so report quota use, not dollars: relative size, and pressure on the 5-hour window. Verification loops multiply token use, so few cheap checks beat many open-ended ones.
- **Model and effort:** recommend a tier and effort for the issue as written (baseline is the issue's `[model=<model>]` tag if present, otherwise default Sonnet; Haiku only for mechanical, tightly specified changes; Opus only for cross-cutting design or repeated failures), and again for after the suggested changes.
- **Cheaper model options:** unless the post-change model is already Haiku, find what keeps the task on its tier: the parts that need design judgment, open-ended verification, or cross-cutting reasoning. For each, propose a scope change that would allow a cheaper tier (specify the exact change in the issue, split the hard part into its own issue, drop it), the resulting model / effort, and what functionality would be lost or deferred so it can become a follow-up issue. Never split out or drop the task's own verification: Cyrus must be able to check its work within the task, so validation that needs a higher tier is a reason the task stays on that tier.

### 3a. Check gaps against available tooling
Before reporting anything from step 3 as something Cyrus can't do or doesn't know (a clarification question, wrong direction, blocker, human prerequisite, or a reason to stay on a higher model tier), check it against the declared tooling. Knowing a tool exists isn't enough: look up what it does, using the MCP server's tool reference or source, the skill's `SKILL.md`, or the plugin's docs. To find a tool's docs, first check the repo's `docs/glossary.md`: use the `Reference` link on the row whose term names that tool, and use its `Not to be confused with` column when checking for clashes. If none is listed, resolve the package named in its `.mcp.json` `command`/`args` (e.g. `uvx --from <pkg>` → PyPI, `npx <pkg>` → npm) and follow the package's homepage or repository link.
- **Covered:** a declared tool or skill handles the step. Drop the gap, and have the draft name that tool or skill in Process notes so Cyrus uses it rather than rediscovering it.
- **Partly covered:** keep only the part no tool handles (e.g. the tool installs packages but can't authenticate to a store). State that narrower gap.
- **Not covered:** report it as usual.
- **Clashing:** two or more declared tools or skills explicitly conflict on the same step, as confirmed from their docs or source (different install paths, competing formatters, one overwriting the other's output). Report this as a wrong direction, and have the draft say which one to use.
- **Possible clash:** the overlap is only inferred, from similar names, descriptions, or apparent scope. Mention it as a possibility, and don't base any wrong direction, suggested change, draft text, or glossary entry on it.
- If a tool's capabilities can't be looked up, say so in Access failures, and mark the gap as unconfirmed rather than stating it as fact.

### 4. Check references
For every URL and embed in the issue and its parent:
- Fetch it (GitHub repo files via `gh`, as above). Report only failures. A failure from the reviewer does not prove failure for Cyrus, so record which environment failed.
- Flag links to deprecated, moved, or wrong-version docs and give the replacement.
- Where a page is blocked, note that its needed content should be captured (e.g. via Claude for Chrome) into the draft, not left as a link.
- Prefer information in the description itself, then the repo, then Linear documents; embeds and links come last.

### 5. Write the draft and reply with the report
Write `draft.md` with YAML frontmatter `issue: <ISSUE-ID>` followed by the proposed rewritten description (goal, objective, acceptance criteria, out of scope, process notes, references), and save `base.json`. Acceptance criteria that ask for verification name an example input (e.g. an attached log) and the result to show in the PR (e.g. the parsed output beside a plain database query), using only what the issue ships plus standard tools. Reword any that could only be met by a verification-only command, flag, column, or mode. Then reply with the report, using the template below, as the chat response. Do not touch Linear.

## Report template

Be direct: state findings, not the review process. Do not restate issue metadata (status, assignee, estimate, milestone); it is in Linear. Keep headings and the scorecard keys exactly as below so reports can be parsed.

```
# <ISSUE-ID> <title>

## Scorecard
| Key | Value |
|---|---|
| Score | <n>/10 |
| Verdict | Ready / Minor edits / Needs rewrite / Blocked |
| Repo | <`[repo=<repo>]`, from the issue's own tag or inferred from the project's Github link, or "unknown: <reason>"> |
| Labels | <full suggested label set, e.g. work approach + routing labels, not model or repo> |
| Model / effort | <`[model=<model>]`> / <low|medium|high> |
| Rounds | <n> |
| Quota | <small|medium|large>, <low|medium|high> 5-hour pressure |
| Blockers | <issue IDs, or "none"> |

## Sufficiency for Cyrus
<one or two sentences: can Cyrus complete this as written, and the main reason if not>

### Clarification questions
(ordered as Cyrus would likely ask them)

### Wrong directions
- **<short name>:** <what Cyrus would likely do and why>

### Blocked / contradictory

## Access failures
| Item | Failure | Environment | Action |
(links, embeds, documents, or repo files the reviewer could not read, after trying `gh` for GitHub content. Environment capabilities never go here. Omit the whole section when there are none.)

## Suggested changes
(ordered; communicate the intended scope more clearly without changing it)

### If implemented
(estimates: score, verdict, rounds, quota, model / effort after the changes, and which clarification questions, wrong directions, and contradictions above would remain)

### Cheaper model options
- **<scope change>:** <model / effort>. Keeps it off <cheaper tier> today: <reason>. Lost or deferred: <functionality, or "nothing">. Follow-up: <issue to create, or "none">.
(omit when the post-change model is already Haiku)

Draft: issue-reviews/<ISSUE-ID>/draft.md
```

The scorecard describes the issue as written and carries values only; reasoning goes in the sections below it or in discuss mode. Omit any `###` subsection that has no entries.

## Discuss

Refine `draft.md` with the user until they are satisfied. Keep edits in the working folder; when a change affects the report's findings, say how in the reply instead of reprinting the whole report. Ask short multiple-choice questions for decisions with a handful of options; go free-form only when the options cannot be narrowed. Do not write to Linear in this mode.

## Commit

Handled by the separate command `/linear-issue-commit <ISSUE-ID>`. When the user is satisfied in discuss mode, remind them the command exists; do not run it or offer to run it for them.

## Multiple issues

If the request names more than one issue, fork into one conversation per issue (or start separate sessions) before running analyze in any of them, each given a read-only sibling list, so the report reaches the user and no conversation sees another issue's draft. Each writes only to its own working folder

## Later (not in scope yet)

Creating issues from a design document or spec: extract the issue hierarchy, run the same review on each draft, create on the commit flag.