---
name: planning
description: This skill should be used when the user asks to "plan an effort", "decompose an effort", "break down work into tasks", "run a decomposition session", "help me plan this", "what stubs should I tackle next", "expand a stub", or asks how to structure tasks in an effort. Provides the effort decomposition methodology and session protocol for progressively breaking effort goals into executable tasks.
---
# Effort Planning and Decomposition

Effort decomposition is the process of progressively breaking a high-level effort goal into actionable tasks. Two frameworks inform the design:

- **Work Breakdown Structure (WBS)** — deliverable-oriented top-down decomposition, organized around *outputs* not activities, with MECE children and defined completion conditions
- **Hierarchical Task Networks (HTN)** — compound tasks decompose via named *methods* (alternative strategies), subtasks carry ordering constraints, decomposition continues until primitive operations are reached

The core constraint: decomposition is **iterative** — each session operates at exactly one level of the hierarchy. Children produced in a session are stubs pending their own future sessions. This prevents premature over-specification on projects not yet fully understood.

## Decomposition Tiers

Every effort goal sits at the root. Below it, the hierarchy follows these tiers:

| Tier | Name | Scope | Duration |
|------|------|-------|----------|
| 0 | **Effort** | The project goal (in README) | open-ended |
| 1 | **Phase / Release** | Major deliverable boundary | months–quarters |
| 2 | **Milestone** | Capability checkpoint within a phase | weeks–months |
| 3 | **Feature / Epic** | User-facing capability | days–weeks |
| 4 | **Story / Component** | Implementation unit within a feature | hours–days |
| 5 | **Atomic Task** | Primitive, directly executable unit | 30 min–4 h |

Tiers are semantic guidance, not strict rules. Shallow efforts may skip tiers. What matters is that each session stays at one level.

## Decomposition Methods

Before generating children for a stub, choose a **decomposition method** — the named strategy by which this compound task breaks apart. Different methods produce fundamentally different child structures, so the choice is consequential. A compound task may have multiple valid methods; the right one depends on context, constraints, and available information.

The method is a *session-time thinking tool*, not persisted metadata. Once children exist, the method is already encoded in their structure and dependency relationships.

| Method | Structure | Use when |
|--------|-----------|----------|
| **Sequential pipeline** | Each child blocks the next | Work has strict ordering by dependency or risk |
| **Parallel tracks** | Children are independent | Independent workstreams can proceed simultaneously |
| **Layer decomposition** | Break by architectural/system layer | Technical work separable by tier (data, logic, UI) |
| **User journey** | Steps follow user/workflow progression | Delivering capability in user-facing increments |
| **Risk-first** | Highest-uncertainty work becomes its own phase | Unknowns could invalidate later work if not resolved first |
| **Phase-gate** | Proceed only if prior deliverable meets threshold | External dependencies or approvals gate progress |

## Deliverable Orientation

Frame children as **deliverables** — things that will *exist or be true* when done — rather than activities. This makes completion criteria unambiguous and prevents scope drift.

| Weak (activity) | Strong (deliverable) |
|-----------------|---------------------|
| Implement auth system | Auth system passes security review and handles 1k req/s |
| Write database schema | Schema document approved, migrations passing in staging |
| Set up CI/CD | All PRs trigger automated test + deploy pipeline |

Define each task's completion condition at creation time as a dataview property in the task notes:

```markdown
- [done:: auth system passes security audit and handles 1k req/s]
```

## Atomicity Criteria

A task is **atomic** (primitive, Tier 5) when it can be directly executed without further planning:
- Fits in 30 min–4 h of uninterrupted work
- Has a single, unambiguous completion condition
- Cannot be split into meaningfully independent parallel work
- Requires no further research or decision-making before starting

If a task fails any criterion, it is a compound task — mark it `#stub` for a future decomposition session.

## Ordering Constraints

Siblings are **parallel by default** — no annotation needed. Sequential dependencies are expressed using the existing `⛔ <uuid>` blocked-by tag, which handles cross-sibling and cross-effort blocking.

```markdown
- [ ] Phase 1: Foundation #parent [effort::6w]
  - [done:: all milestone deliverables shipped and verified in staging]
  - [ ] Database schema and migrations 🆔 fa3c12 #stub [effort::1w]
    - [done:: schema approved, migrations passing in staging]
  - [ ] Auth system #stub [effort::3w] ⛔ fa3c12
    - [done:: passes security audit and handles 1k req/s]
  - [ ] CI/CD pipeline #stub [effort::1w]
    - [done:: all PRs trigger automated test + deploy]
```

The dependency structure itself encodes the decomposition method — sequential pipelines produce blocking chains; parallel tracks produce no cross-dependencies. No separate method annotation is needed.

## Session Protocol

A decomposition session expands one or more `#stub` tasks at a single tier.

### Pre-session
1. **Select a tier** — decide which level to work at this session
2. **Select targets** — identify `#stub` tasks at that tier (siblings work well together)
3. **Read context** — the effort README, parent task notes, and sibling tasks

### Decomposition
4. **Choose a method** — pick the decomposition strategy for each target stub
5. **Generate children as deliverables** — MECE: mutually exclusive scope, collectively exhaustive coverage of parent
6. **Define completion conditions** — add `[done:: ...]` to each child's notes at creation time
7. **Mark dependencies** — add `⛔ <uuid>` where one child must precede another; leave unmarked otherwise
8. **Estimate** — assign rough estimates where obvious; leave blank otherwise
9. **Mark atomicity** — tasks meeting primitive criteria get no `#stub`; everything else does

### Post-session
10. **Update TASKS.md** — add children under parent, mark parent `#parent`
11. **Identify next session** — which stubs are highest priority to decompose next?

### Constraints
- **One tier per session**: do not decompose a parent and then a child in the same session. Review the whole tier first.
- **MECE before depth**: a poorly-partitioned tier is worse than fewer, well-scoped stubs.
- **No scope addition**: children should not add scope not implied by the parent. New scope goes as a sibling stub at the parent's tier, flagged for review.
- **Method first**: choosing children before choosing a method produces arbitrary structure. Pick the method first.

## Task Markup

```markdown
- [ ] Phase: Core Infrastructure #parent [effort::3mo]
  - [done:: auth, schema, and CI/CD all verified in staging]
  - [ ] Auth system #stub [effort::3w]
    - [done:: passes security audit and handles 1k req/s]
  - [ ] Database schema #stub 🆔 db001 [effort::1w]
    - [done:: schema approved, migrations passing in staging]
  - [ ] CI/CD pipeline #stub [effort::1w] ⛔ db001
    - [done:: all PRs trigger automated test+deploy]
```

| Tag | Meaning |
|-----|---------|
| `#stub` | Compound task not yet decomposed — needs a future session |
| `#parent` | Has been decomposed — children are the source of truth |
| `[done:: <condition>]` | Completion condition defined at creation, in task notes |
| `[effort::Xd]` | Rough estimate (sum of children need not match parent) |

## Decomposition Progression

```
README (Tier 0 goal)
  └─ Session A: Tier 1 phases as stubs
       └─ Session B: Phase 1 → Tier 2 milestones as stubs
            └─ Session C: Milestone 1.1 → Tier 3 features as stubs
                 └─ Session D: Feature 1.1.1 → atomic tasks
```

Sessions on different branches are independent and can interleave freely. Only decompose as deep as needed to start executing — not all branches need to reach Tier 5 before work begins.

## Starting the First Session

The first session (Tier 0 → Tier 1) answers:

> "What are the major phases that constitute this effort, what deliverable exists at the end of each, and in what order must they complete?"

Input is the effort README. Output is 2–5 Tier 1 stubs in `01 TASKS.md`. Producing 8+ stubs means working at the wrong tier.

## Reviewing Decomposition Depth

Audit the current state by reading `TASKS.md` through different lenses:

- **CEO view**: top-level tasks only — is the roadmap coherent?
- **Manager view**: 2–3 levels — is the plan realistic and well-sequenced?
- **Worker view**: leaf tasks only (no subtasks) — is the work queue executable?

If the worker view contains non-atomic tasks, those are stubs needing another session.

## Integration With Effort and Task Workflows

- Use `/effort-workflow:new` to create the effort before starting decomposition
- Use `/task-workflow:add` to record tasks produced in a session
- Use `/task-workflow:list` to find all remaining `#stub` tasks
- Decomposition sessions fit naturally into planning reviews

## Additional Resources

- **`references/anti-patterns.md`** — Common decomposition mistakes and how to fix them
