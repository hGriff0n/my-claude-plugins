"""GET /efforts — list efforts, optionally filtered by status."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.efforts import Effort, EffortStatus
from schemas.tasks import TaskStatus

router = APIRouter()


class ListEffortsResponse(BaseModel):
    efforts: list[Effort]
    next_page_token: Optional[str] = None


@router.get(
    "/efforts",
    operation_id="effort_list",
    response_model=ListEffortsResponse,
)
def effort_list(
    status: Optional[EffortStatus] = Query(None),
    include_task_stats: bool = Query(False),
    page_size: Optional[int] = Query(None),
    page_token: Optional[str] = Query(None),
    app: App = Depends(get_app),
) -> ListEffortsResponse:
    efforts = app.db.query('SELECT * FROM "effort"')
    if status is not None:
        efforts = [e for e in efforts if e.status == status]

    zero = {s.value: 0 for s in TaskStatus}

    if include_task_stats:
        try:
            tasks = app.db.query('SELECT * FROM "task"')
        except ValueError:
            tasks = []
        per_effort: dict[str, dict[str, int]] = {}
        for t in tasks:
            bucket = per_effort.setdefault(t.effort, dict(zero))
            bucket[t.status.value] = bucket.get(t.status.value, 0) + 1
        for e in efforts:
            e.display.task_stats.num_by_status = per_effort.get(e.name, dict(zero))
    else:
        for e in efforts:
            e.display.task_stats.num_by_status = dict(zero)

    return ListEffortsResponse(efforts=efforts, next_page_token=None)
