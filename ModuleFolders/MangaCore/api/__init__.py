"""FastAPI router bundle for MangaCore."""

from fastapi import APIRouter

from .routesEditor import router as editor_router
from .routesExport import router as export_router
from .routesJobs import router as jobs_router
from .routesModels import router as models_router
from .routesPages import router as pages_router
from .routesPipeline import router as pipeline_router
from .routesProjects import router as projects_router

router = APIRouter()
for child_router in (
    projects_router,
    models_router,
    pages_router,
    pipeline_router,
    editor_router,
    jobs_router,
    export_router,
):
    router.include_router(child_router)

__all__ = ["router"]
