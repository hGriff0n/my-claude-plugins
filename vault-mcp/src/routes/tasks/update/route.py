"""PATCH /tasks/{id} — update a task's mutable fields."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.tasks import Dependencies, Task, TaskStatus
from schemas.time import TimeBlock
from vault.tasks.parser import (
    UpdateDependencies,
    UpdateMetadata,
    UpdateStatus,
    UpdateText,
)

router = APIRouter()


class UpdateTaskRequest(BaseModel):
    text: Optional[str] = None
    status: Optional[TaskStatus] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[Dependencies] = None
    time_details: Optional[TimeBlock] = None


@router.patch(
    "/tasks/{id}",
    operation_id="task_update",
    response_model=Task,
)
def task_update(
    id: str, body: UpdateTaskRequest, app: App = Depends(get_app)
) -> Task:
    task = next(
        (t for t in app.db.query('SELECT * FROM "task"') if t.id == id),
        None,
    )
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{id}' not found")

    if body.dependencies is not None:
        all_ids = {t.id for t in app.db.query('SELECT * FROM "task"')}
        for ref in list(body.dependencies.blocked) + (
            [body.dependencies.parent] if body.dependencies.parent else []
        ):
            if ref and ref not in all_ids:
                raise HTTPException(
                    status_code=400, detail=f"Unknown referenced task '{ref}'"
                )

    try:
        if body.text is not None:
            app.task_parser.update(task, UpdateText(body.text))
        if body.status is not None:
            app.task_parser.update(task, UpdateStatus(body.status))
        if body.tags is not None or body.time_details is not None:
            app.task_parser.update(
                task,
                UpdateMetadata(tags=body.tags, time_details=body.time_details),
            )
        if body.dependencies is not None:
            app.task_parser.update(task, UpdateDependencies(body.dependencies))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"update failed: {e}")

    return task
