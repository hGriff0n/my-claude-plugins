"""REST API routes for effort operations."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tools.effort_tools import (
    handle_effort_focus,
    handle_effort_get,
    handle_effort_get_focus,
    handle_effort_list,
    handle_effort_scan,
    handle_effort_unfocus,
)


class EffortFocusBody(BaseModel):
    name: str


def register_effort_routes(app_router: APIRouter, cache) -> None:
    """Attach effort REST routes that use the shared cache."""

    @app_router.get("/efforts")
    def list_efforts(
        status: Optional[str] = Query(None),
        include_task_counts: bool = Query(False),
    ):
        return handle_effort_list(
            cache, status=status, include_task_counts=include_task_counts
        )

    # Focus routes before the {name} catch-all
    @app_router.get("/efforts/focus")
    def get_focus():
        return handle_effort_get_focus(cache)

    @app_router.put("/efforts/focus")
    def set_focus(body: EffortFocusBody):
        try:
            return handle_effort_focus(cache, name=body.name)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app_router.delete("/efforts/focus")
    def clear_focus():
        return handle_effort_unfocus(cache)

    @app_router.post("/efforts/scan")
    def scan_efforts():
        return handle_effort_scan(cache)

    @app_router.get("/efforts/{name}")
    def get_effort(name: str):
        result = handle_effort_get(cache, name=name)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
