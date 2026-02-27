"""REST API routes for task operations."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tools.task_tools import (
    handle_cache_status,
    handle_task_add,
    handle_task_blockers,
    handle_task_get,
    handle_task_list,
    handle_task_update,
)


class TaskAddBody(BaseModel):
    title: str
    file_path: str
    section: Optional[str] = None
    status: str = "open"
    due: Optional[str] = None
    scheduled: Optional[str] = None
    estimate: Optional[str] = None
    blocked_by: Optional[str] = None
    parent_id: Optional[str] = None
    atomic: bool = False


class TaskUpdateBody(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    due: Optional[str] = None
    scheduled: Optional[str] = None
    estimate: Optional[str] = None
    blocked_by: Optional[str] = None
    unblock: Optional[str] = None


def register_task_routes(app_router: APIRouter, cache) -> None:
    """Attach task REST routes that use the shared cache."""

    @app_router.get("/tasks")
    def list_tasks(
        status: str = Query("open,in-progress"),
        effort: Optional[str] = Query(None),
        due_before: Optional[str] = Query(None),
        scheduled_before: Optional[str] = Query(None),
        scheduled_on: Optional[str] = Query(None),
        stub: Optional[bool] = Query(None),
        blocked: Optional[bool] = Query(None),
        atomic: Optional[bool] = Query(None),
        file_path: Optional[str] = Query(None),
        parent_id: Optional[str] = Query(None),
        include_subtasks: bool = Query(False),
        limit: int = Query(200),
    ):
        return handle_task_list(
            cache,
            status=status,
            effort=effort,
            due_before=due_before,
            scheduled_before=scheduled_before,
            scheduled_on=scheduled_on,
            stub=stub,
            blocked=blocked,
            atomic=atomic,
            file_path=file_path,
            parent_id=parent_id,
            include_subtasks=include_subtasks,
            limit=limit,
        )

    @app_router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        result = handle_task_get(cache, task_id=task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.post("/tasks", status_code=201)
    def add_task(body: TaskAddBody):
        try:
            return handle_task_add(cache, **body.model_dump())
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app_router.patch("/tasks/{task_id}")
    def update_task(task_id: str, body: TaskUpdateBody):
        try:
            result = handle_task_update(cache, task_id=task_id, **body.model_dump())
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.get("/tasks/{task_id}/blockers")
    def get_blockers(task_id: str):
        result = handle_task_blockers(cache, task_id=task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.get("/cache/status")
    def get_cache_status():
        return handle_cache_status(cache)
