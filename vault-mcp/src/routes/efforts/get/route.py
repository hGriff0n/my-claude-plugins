"""GET /efforts/{name} — fetch a single effort with live task stats."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.efforts import Effort
from schemas.tasks import TaskStatus

router = APIRouter()


class GetEffortRequest(BaseModel):
    name: str


@router.get(
    "/efforts/{name}",
    operation_id="effort_get",
    response_model=Effort,
)
def effort_get(name: str, app: App = Depends(get_app)) -> Effort:
    effort = next(
        (e for e in app.db.query('SELECT * FROM "effort"') if e.name == name),
        None,
    )
    if effort is None:
        raise HTTPException(status_code=404, detail=f"Effort '{name}' not found")

    counts = {s.value: 0 for s in TaskStatus}
    try:
        tasks = app.db.query('SELECT * FROM "task"')
    except ValueError:
        tasks = []
    for t in tasks:
        if t.effort == name:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1

    effort.display.task_stats.num_by_status = counts
    return effort
