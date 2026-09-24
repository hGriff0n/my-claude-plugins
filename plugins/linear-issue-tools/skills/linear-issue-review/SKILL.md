---
name: linear-issue-review
description: Review a Linear issue's readiness for Cyrus and refine a rewrite with the user. Use when asked to review, audit, or improve a Linear issue, whether one is ready for Cyrus, or why Cyrus would get stuck on one.
argument-hint: <analyze|discuss> <ISSUE-ID>
---

# Linear issue review (pre-Cyrus)

Rubric source: https://www.atcyrus.com/docs/writing-great-issues. Re-fetch it each run; if it cannot be fetched, say so and use the criteria below.

## Modes

- **analyze** `<ISSUE-ID>`: gather context, write the draft, and reply with the report. Read-only in Linear. Then continue in discuss mode in the same conversation.
- **discuss** `<ISSUE-ID>`: refine that issue's draft with the user. In a new conversation, resume from the working folder; the report is not saved, so re-run analyze if the user wants it again. One issue per conversation; do not load other issues' drafts.
- **commit**: not part of this skill. Writing to Linear is done only by the separate user-typed command `/linear-issue-commit <ISSUE-ID>` (see `commands/linear-issue-commit.md` in this plugin). This skill never writes to Linear.

Working folder (temporary): `./issue-reviews/<ISSUE-ID>/` containing `draft.md` (proposed description) and `base.json` (the issue as read: description, `updatedAt`). The commit command deletes it after a successful write. The report is never written to a file.

## Environment config

Cyrus's environment differs from the reviewer's machine, so judge feasibility against a config, not against what is installed locally.

1. Look for a Linear document titled **"Cyrus Environment"** in the issue's project. If none, look at workspace level. If none, the project is not integrated with Cyrus: report that under Access failures and review the issue text only, without assuming any repos, tools, or labels. Do not substitute the reviewer's local setup.
2. Follow every link in the document, especially links to other Linear documents, and merge their content. A project document should be able to say "same as workspace, plus X" instead of repeating it. Guard against link loops and stop at depth 3.
3. Expected contents: tools, skills and MCP servers Cyrus has; how tests are run; repo routing rules; label and model conventions; known limits (cannot press keys, cannot buy assets, cannot log in to stores).

Repo names come only from this document. Names that appear in the issue text are the author's claims: quote them as such, and do not read ordinary words (e.g. "assets", "game") as repo names.

Do not hard-code repo, branch, or engine/package versions in issues when the repo can answer them; check whether Cyrus can read them itself (e.g. `ProjectSettings/ProjectVersion.txt`, `Packages/manifest.json`).

## Analyze

### 1. Gather context (read-only)
Issue, comments, sub-issues, parent, siblings, blocking/blocked-by and related relations, project and milestone descriptions, and documents. Read siblings and relations together with the issue: a problem is often only visible across issues. Note that files embedded in a description have signed URLs that expire in about five minutes and do not appear under `attachments`; download and read them immediately.

### 2. Score against the Cyrus guide
Rate each criterion Met / Partial / Missing: title, context, objective, acceptance criteria (verifiable and self-checkable), validation approach, output format, process notes, references, routing (repo, labels), dependencies. Flag unfilled template placeholders (`<...>`) and empty sections automatically. Give an overall score out of 10. The per-criterion ratings are working notes, not report content: each gap should surface as a clarification question, wrong direction, or contradiction it would cause, and gaps that cause none of these (e.g. a vague title, empty References) go to Suggested changes.

### 3. Search for problems
- **Clarification:** the specific questions Cyrus would post, in its likely order.
- **Wrong direction:** misinterpretations, scope creep into sibling issues, wrong API or version, guessing at unspecified choices, claiming done without verification, edits that break tooling (e.g. missing metadata files, hand-edited generated files), being unable to verify because of environment limits, and labels that mislead.
- **Blocked or contradictory:** unresolved blockers on a queued issue; text implying a dependency that the relations do not show (and the reverse); statements that conflict with comments or the parent.
- **Iterations and quota:** expected rounds as written and after the suggested changes. The user is on a subscription plan, so report quota use, not dollars: relative size, and pressure on the 5-hour window. Verification loops multiply token use, so few cheap checks beat many open-ended ones.
- **Model and effort:** recommend a tier and effort for the issue as written (default Sonnet; Haiku only for mechanical, tightly specified changes; Opus only for cross-cutting design or repeated failures), and again for after the suggested changes.
- **Cheaper model options:** unless the post-change model is already Haiku, find what keeps the task on its tier: the parts that need design judgment, open-ended verification, or cross-cutting reasoning. For each, propose a scope change that would allow a cheaper tier (specify the exact change in the issue, split the hard part into its own issue, drop it), the resulting model / effort, and what functionality would be lost or deferred so it can become a follow-up issue. Never split out or drop the task's own verification: Cyrus must be able to check its work within the task, so validation that needs a higher tier is a reason the task stays on that tier.

### 4. Check references
For every URL and embed in the issue and its parent:
- Fetch it. Report only failures. A failure from the reviewer does not prove failure for Cyrus, so record which environment failed.
- Flag links to deprecated, moved, or wrong-version docs and give the replacement.
- Where a page is blocked, note that its needed content should be captured (e.g. via Claude for Chrome) into the draft, not left as a link.
- Prefer information in the description itself, then the repo, then Linear documents; embeds and links come last.

### 5. Write the draft and reply with the report
Write `draft.md` with the proposed rewritten description (goal, objective, acceptance criteria, out of scope, process notes, references) and save `base.json`. Then reply with the report, using the template below, as the chat response. Do not touch Linear.

## Report template

Be direct: state findings, not the review process. Do not restate issue metadata (status, assignee, estimate, milestone); it is in Linear. Keep headings and the scorecard keys exactly as below so reports can be parsed.

```
# <ISSUE-ID> <title>

## Scorecard
| Key | Value |
|---|---|
| Score | <n>/10 |
| Verdict | Ready / Minor edits / Needs rewrite / Blocked |
| Repo | <[repo=...] tag from the Cyrus Environment map, or "unknown: <reason>"> |
| Labels | <full suggested label set, e.g. `Sonnet`, `tooling`> |
| Model / effort | <tier> / <low|medium|high> |
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
(links, embeds, documents or config that could not be read, fetched, or verified, including a missing Cyrus Environment document. Omit the whole section when there are none.)

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

Run analyze in a separate conversation per issue (a separate session or fork), each given a read-only sibling list, so the report reaches the user and no conversation sees another issue's draft. Each writes only to its own working folder and has no Linear write access.

## Later (not in scope yet)

Creating issues from a design document or spec: extract the issue hierarchy, run the same review on each draft, create on the commit flag.
