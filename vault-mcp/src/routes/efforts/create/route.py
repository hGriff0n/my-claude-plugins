"""POST /efforts — scaffold a new active effort."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.efforts import Effort
from vault.efforts.parser import CreateEffort

router = APIRouter()


class CreateEffortRequest(BaseModel):
    name: str


@router.post(
    "/efforts",
    status_code=201,
    operation_id="effort_create",
    response_model=Effort,
)
def effort_create(body: CreateEffortRequest, app: App = Depends(get_app)) -> Effort:
    name = body.name

    existing = next(
        (e for e in app.db.query('SELECT * FROM "effort"') if e.name == name),
        None,
    )
    if existing is not None:
        raise HTTPException(
            status_code=400, detail=f"Effort '{name}' already exists"
        )

    parser = app.effort_parser
    folder = parser.vault_root / "efforts" / name
    try:
        parser.write(_new_effort(name), CreateEffort())
    except FileExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"scaffold failed: {e}")

    parsed = parser.parse(folder)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail=f"Effort '{name}' scaffolded but not recognized after parse",
        )
    [effort] = parsed
    app.db.update(effort)
    return effort


# rename as "placeholder" means something else. This is more of a "new effort"
def _new_effort(name: str) -> Effort:
    from datetime import date
    from pathlib import Path

    from schemas.efforts import DisplayDetails, EffortStatus, TaskStats
    from schemas.tasks import TaskStatus
    from schemas.time import TimeBlock

    today = date.today()
    return Effort(
        name=name,
        path=Path(f"efforts/{name}"),
        status=EffortStatus.ACTIVE,
        description="",
        time_details=TimeBlock(
            created=today, last_updated=today, due=today, scheduled=today
        ),
        display=DisplayDetails(
            task_stats=TaskStats(num_by_status={s.value: 0 for s in TaskStatus})
        ),
    )
