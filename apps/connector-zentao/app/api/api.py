from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.zentao import router as zentao_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(zentao_router, prefix="/zentao", tags=["zentao"])
