from fastapi import APIRouter

from .crud import db
from .views import chaospad_generic_router
from .views_api import chaospad_api_router

chaospad_ext: APIRouter = APIRouter(prefix="/chaospad", tags=["ChaosPad"])
chaospad_ext.include_router(chaospad_generic_router)
chaospad_ext.include_router(chaospad_api_router)


chaospad_static_files = [
    {
        "path": "/chaospad/static",
        "name": "chaospad_static",
    }
]
__all__ = [
    "chaospad_ext",
    "chaospad_static_files",
    "db",
]
