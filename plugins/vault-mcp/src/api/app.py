"""FastAPI application factory for the vault REST API."""

from fastapi import APIRouter, FastAPI

from api.effort_routes import register_effort_routes
from api.task_routes import register_task_routes


def create_app(cache) -> FastAPI:
    """Build and return a FastAPI app wired to the given VaultCache."""
    app = FastAPI(title="vault-mcp", docs_url="/api/docs", openapi_url="/api/openapi.json")

    api = APIRouter(prefix="/api")
    register_task_routes(api, cache)
    register_effort_routes(api, cache)
    app.include_router(api)

    return app
