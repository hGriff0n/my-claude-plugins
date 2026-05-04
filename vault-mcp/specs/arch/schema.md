# Schema Spec Template

Defines the contract for a system's domain types. Each system owns one OpenAPI document (`specs/systems/<name>/schema.yaml`) which is the source of truth; the corresponding pydantic module (`src/schemas/<name>.py`) is generated from it.

## Source of truth

- **`specs/systems/<name>/schema.yaml`** — OpenAPI 3.x document. Hand-edited. Defines all domain types and enums for the system.
- **`src/schemas/<name>.py`** — pydantic v2 module, generated from the yaml. Checked in. Never hand-edited after the initial bootstrap; each file carries a header marking it as generated.

The system readme (`arch/system.md`) references the yaml from its `## Resource Schema` section and lists which OpenAPI types should be registered as database tables.

## Generation

Generator: [`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator), pydantic v2 output.

Invocation (run from repo root, once per system):

```
datamodel-codegen \
  --input specs/systems/<name>/schema.yaml \
  --input-file-type openapi \
  --output src/schemas/<name>.py \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --use-union-operator \
  --target-python-version 3.11
```

Regenerate whenever `schema.yaml` changes. The generated file is committed so consumers can import it without running the codegen step.

## Contents of `schema.yaml`

- **Pydantic-equivalent models** for each domain object (e.g. `Effort`, `Task`).
- **Enums** that are part of the domain (e.g. `EffortStatus`).
- **Cross-system references** by name (e.g. a task field typed as an effort name) are allowed; codegen resolves them via shared `components.schemas` entries that may be defined in a sibling `specs/systems/_shared/schema.yaml` if reused.

## What does NOT belong in the system schema

- Endpoint-specific request/response wrappers (`GetEffortRequest`, `ListEffortsResponse`, …) — those are pydantic models defined directly in the owning `route.py` (or `routes/<system>/models.py` if shared across routes within a system).
- Parser-internal scratch types — those stay private to `src/vault/<system>/`.
- Database-internal types (e.g. an index key, a cache entry).

## Imports (generated module)

- The generated `src/schemas/<name>.py` imports only from stdlib, pydantic, and other `src/schemas/` modules.
- No imports from `database/`, `routes/`, or `vault/`.

## Initial bootstrap

The yaml files for existing systems are seeded once from the current hand-written `src/schemas/*.py`. After the bootstrap, the direction reverses: edit yaml, regenerate py.
