"""GET /tasks — list tasks with optional filters."""

from datetime import date
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
    effort: Optional[list[str]] = Query(None),
    status: Optional[list[TaskStatus]] = Query(None),
    type: Optional[TaskType] = Query(None),
    tag: Optional[list[str]] = Query(None),
    due_before: Optional[date] = Query(None),
    scheduled_before: Optional[date] = Query(None),
    page_size: Optional[int] = Query(None),
    page_token: Optional[str] = Query(None),
    app: App = Depends(get_app),
) -> ListTasksResponse:
    conditions: list[str] = []
    params: list = []
    if effort:
        conditions.append(f'"effort" IN ({", ".join("?" * len(effort))})')
        params.extend(effort)
    if status:
        conditions.append(f'"status" IN ({", ".join("?" * len(status))})')
        params.extend(s.value for s in status)
    if type is not None:
        conditions.append('"type" = ?')
        params.append(type.value)
    if due_before is not None and scheduled_before is not None:
        conditions.append(
            '("time_details.due" <= ? OR "time_details.scheduled" <= ?)'
        )
        params.append(due_before.isoformat())
        params.append(scheduled_before.isoformat())
    elif due_before is not None:
        conditions.append('"time_details.due" <= ?')
        params.append(due_before.isoformat())
    elif scheduled_before is not None:
        conditions.append('"time_details.scheduled" <= ?')
        params.append(scheduled_before.isoformat())
    if tag:
        tag_clauses = []
        for t in tag:
            tag_clauses.append(
                'EXISTS (SELECT 1 FROM json_each("task"."tags") '
                'WHERE value = ? OR value LIKE ?)'
            )
            params.extend([t, f"{t}:%"])
        conditions.append("(" + " OR ".join(tag_clauses) + ")")

    sql = 'SELECT * FROM "task"'
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    tasks = app.db.query(sql, tuple(params))
    return ListTasksResponse(tasks=tasks, next_page_token=None)
