"""POST /efforts/{name}/move — move an effort between active/backlog/archive."""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routes.deps import App, get_app
from schemas.efforts import Effort, EffortStatus
from vault.efforts.parser import MoveEffort

router = APIRouter()

MoveTarget = Literal["active", "backlog", "archive"]


class MoveEffortRequest(BaseModel):
    target: MoveTarget


class MoveEffortResponse(BaseModel):
    effort: Optional[Effort] = None
    archived: bool = False


@router.post(
    "/efforts/{name}/move",
    operation_id="effort_move",
    response_model=MoveEffortResponse,
)
def effort_move(
    name: str, body: MoveEffortRequest, app: App = Depends(get_app)
) -> MoveEffortResponse:
    prev = next(
        (e for e in app.db.query('SELECT * FROM "effort"') if e.name == name),
        None,
    )
    if prev is None:
        raise HTTPException(status_code=404, detail=f"Effort '{name}' not found")

    target = body.target
    current_state = "active" if prev.status == EffortStatus.ACTIVE else "backlog"
    if target == current_state:
        return MoveEffortResponse(effort=prev, archived=False)

    parser = app.effort_parser
    try:
        parser.write(prev, MoveEffort(target=target))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"move failed: {e}")

    if target == "archive":
        app.db.update(prev, delete=True)
        return MoveEffortResponse(effort=None, archived=True)

    folder_root = parser.vault_root / "efforts"
    folder = folder_root / "__backlog" / name if target == "backlog" else folder_root / name
    parsed = parser.parse(folder)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail=f"Effort '{name}' moved but not recognized after parse",
        )
    [effort] = parsed
    app.db.update(effort)
    return MoveEffortResponse(effort=effort, archived=False)
