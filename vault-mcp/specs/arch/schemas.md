# Schemas Spec Template

Defines the contract every `src/schemas/<system>.py` module must follow. Implementation specs (e.g. `src/database/efforts/readme.md`, route readmes) reference the resource types defined here.

## Purpose

`src/schemas/<system>.py` holds the canonical domain types for one system — the shape used by both `db.<system>` (in-memory state) and route responses (wire format). One pydantic model is the single source of truth for what an `Effort`, `Task`, etc. *is*.

## Files

One file per system: `src/schemas/<system>.py`. No sub-folders, no per-type files.

## Contents

- **Pydantic v2 models** for each domain object (e.g. `Effort`, `Task`).
- **Enums** that are part of the domain (e.g. `EffortStatus`).
- **Methods on the models** for state modification (e.g. `task.add_blocker(id)`). No I/O on these methods.

## What does NOT belong here

- Endpoint-specific request/response wrappers (`GetEffortRequest`, `ListEffortsResponse`, …) — those live in the owning `route.py`, or in `routes/<system>/models.py` if shared across routes within a system.
- Parser-internal scratch types — those stay private to `vault/<system>/`.
- Database-internal types (e.g. an index key, a cache entry) — those stay in `db.py`.

## Imports

- Imports only from `utils/` and stdlib. No imports from `database/`, `routes/`, or `vault/`.
- May import from another `schemas/<other_system>` for cross-system type references (e.g. a task referencing an effort name as a typed field).

## Consumers

- `db.<system>` imports the resource types and holds live instances.
- `route.py` files import the resource types and reference them in their request/response wrappers (per `arch/routes.md`).
- `vault/<system>/parser` imports the resource types when constructing instances during a scan.
