"""Joined router for all vault-mcp routes.

Imports each `<system>/<op>/route.py` module and includes its `router` into
a single top-level `APIRouter`. The server registers this one router.
"""

from fastapi import APIRouter

from routes.efforts.create.route import router as efforts_create
from routes.efforts.get.route import router as efforts_get
from routes.efforts.list.route import router as efforts_list
from routes.efforts.move.route import router as efforts_move
# from routes.tasks.archive.route import router as tasks_archive
# from routes.tasks.create.route import router as tasks_create
# from routes.tasks.get.route import router as tasks_get
# from routes.tasks.list.route import router as tasks_list
# from routes.tasks.update.route import router as tasks_update

router = APIRouter()

for r in (
    efforts_create,
    efforts_get,
    efforts_list,
    efforts_move,
    # tasks_archive,
    # tasks_create,
    # tasks_get,
    # tasks_list,
    # tasks_update,
):
    router.include_router(r)
