"""REST API routes for vault-mcp."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.task_handlers import (
    handle_cache_status,
    handle_task_add,
    handle_task_blockers,
    handle_task_get,
    handle_task_list,
    handle_task_update,
)
from api.effort_handlers import (
    handle_effort_create,
    handle_effort_get,
    handle_effort_list,
    handle_effort_move,
    handle_effort_scan,
)


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------


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


class TaskUpdateBody(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    due: Optional[str] = None
    scheduled: Optional[str] = None
    estimate: Optional[str] = None
    blocked_by: Optional[str] = None
    unblock: Optional[str] = None


class EffortCreateBody(BaseModel):
    name: str


class EffortMoveBody(BaseModel):
    backlog: bool = False
    archive: bool = False


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_routes(app_router: APIRouter, cache) -> None:
    """Attach all REST routes that use the shared cache."""

    # --- Task routes ---

    @app_router.get("/tasks")
    def list_tasks(
        status: str = Query("open,in-progress"),
        effort: Optional[str] = Query(None),
        due_before: Optional[str] = Query(None),
        scheduled_before: Optional[str] = Query(None),
        scheduled_on: Optional[str] = Query(None),
        stub: Optional[bool] = Query(None),
        blocked: Optional[bool] = Query(None),
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

    # --- Effort routes ---

    @app_router.get("/efforts")
    def list_efforts(
        status: Optional[str] = Query(None),
        include_task_counts: bool = Query(False),
    ):
        return handle_effort_list(
            cache, status=status, include_task_counts=include_task_counts
        )

    @app_router.post("/efforts", status_code=201)
    def create_effort(body: EffortCreateBody):
        try:
            result = handle_effort_create(cache, name=body.name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result

    @app_router.post("/efforts/scan")
    def scan_efforts():
        return handle_effort_scan(cache)

    @app_router.get("/efforts/{name}")
    def get_effort(name: str):
        result = handle_effort_get(cache, name=name)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app_router.post("/efforts/{name}/move")
    def move_effort(name: str, body: EffortMoveBody):
        try:
            result = handle_effort_move(
                cache, name=name, backlog=body.backlog, archive=body.archive
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if "error" in result:
            status_code = 404 if "not found" in result["error"] else 400
            raise HTTPException(status_code=status_code, detail=result["error"])
        return result
