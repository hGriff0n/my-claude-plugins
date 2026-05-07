"""POST /tasks/{id}/archive — archive a closed task."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.tasks import TaskStatus
from vault.tasks.parser import ArchiveTask

router = APIRouter()


class ArchiveTaskResponse(BaseModel):
    archived: bool


@router.post(
    "/tasks/{id}/archive",
    operation_id="task_archive",
    response_model=ArchiveTaskResponse,
)
def task_archive(id: str, app: App = Depends(get_app)) -> ArchiveTaskResponse:
    task = next(
        (t for t in app.db.query('SELECT * FROM "task"') if t.id == id),
        None,
    )
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{id}' not found")
    if task.status != TaskStatus.CLOSED:
        raise HTTPException(
            status_code=400, detail=f"Task '{id}' is not CLOSED"
        )
    app.task_parser.update(task, ArchiveTask())
    return ArchiveTaskResponse(archived=True)
