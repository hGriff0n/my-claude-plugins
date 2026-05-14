"""GET /tasks/{id} — fetch a task by id."""

from fastapi import APIRouter, Depends, HTTPException

from routes.deps import App, get_app
from schemas.tasks import Task

router = APIRouter()


@router.get(
    "/tasks/{id}",
    operation_id="task_get",
    response_model=Task,
)
def task_get(id: str, app: App = Depends(get_app)) -> Task:
    task = next(
        (t for t in app.db.query('SELECT * FROM "task"') if t.id == id),
        None,
    )
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{id}' not found")
    return task
