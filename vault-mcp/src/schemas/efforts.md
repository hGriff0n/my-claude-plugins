# Efforts Schema

Implements `specs/arch/schemas.md` for the efforts system. See `specs/systems/efforts.md` for the domain model.

## Types

`EffortStatus` enum:
- `ACTIVE`
- `BACKLOG`

`Effort` pydantic model:
- `name: str`
- `path: Path`
- `status: EffortStatus`
- `tasks_file: Path | None`
