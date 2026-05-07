"""POST /tasks — create a new task in the root taskfile or under an effort."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.tasks import Dependencies, Task, TaskStatus, TaskType
from schemas.time import TimeBlock
from vault.tasks.parser import CreateTask, _NULL_DATE

router = APIRouter()


class CreateTaskRequest(BaseModel):
    text: str
    effort: str = "none"
    status: TaskStatus = TaskStatus.OPEN
    type: TaskType = TaskType.TASK
    parent: Optional[str] = None


@router.post(
    "/tasks",
    status_code=201,
    operation_id="task_create",
    response_model=Task,
)
def task_create(body: CreateTaskRequest, app: App = Depends(get_app)) -> Task:
    if body.effort != "none":
        existing = next(
            (e for e in app.db.query('SELECT * FROM "effort"') if e.name == body.effort),
            None,
        )
        if existing is None:
            raise HTTPException(
                status_code=400, detail=f"Effort '{body.effort}' not found"
            )

    parent_id = ""
    if body.parent:
        parent = next(
            (t for t in app.db.query('SELECT * FROM "task"') if t.id == body.parent),
            None,
        )
        if parent is None:
            raise HTTPException(
                status_code=400, detail=f"Parent task '{body.parent}' not found"
            )
        parent_id = body.parent

    task = Task(
        id="",
        type=body.type,
        status=body.status,
        text=body.text,
        effort=body.effort,
        notes=[],
        tags=[],
        dependencies=Dependencies(blocked=[], parent=parent_id, children=[]),
        time_details=TimeBlock(
            created=_NULL_DATE,
            last_updated=_NULL_DATE,
            due=_NULL_DATE,
            scheduled=_NULL_DATE,
        ),
    )
    app.task_parser.update(task, CreateTask())
    return task
