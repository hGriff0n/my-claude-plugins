"""GET /tasks — list tasks with optional filters."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.tasks import Task, TaskStatus, TaskType

router = APIRouter()


class ListTasksResponse(BaseModel):
    tasks: list[Task]
    next_page_token: Optional[str] = None


@router.get(
    "/tasks",
    operation_id="task_list",
    response_model=ListTasksResponse,
)
def task_list(
    effort: Optional[str] = Query(None),
    status: Optional[TaskStatus] = Query(None),
    type: Optional[TaskType] = Query(None),
    tag: Optional[str] = Query(None),
    page_size: Optional[int] = Query(None),
    page_token: Optional[str] = Query(None),
    app: App = Depends(get_app),
) -> ListTasksResponse:
    tasks = app.db.query('SELECT * FROM "task"')
    if effort is not None:
        tasks = [t for t in tasks if t.effort == effort]
    if status is not None:
        tasks = [t for t in tasks if t.status == status]
    if type is not None:
        tasks = [t for t in tasks if t.type == type]
    if tag is not None:
        tasks = [
            t for t in tasks
            if any(entry == tag or entry.split(":", 1)[0] == tag for entry in t.tags)
        ]
    return ListTasksResponse(tasks=tasks, next_page_token=None)
