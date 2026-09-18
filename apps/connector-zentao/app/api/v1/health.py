from fastapi import APIRouter, Request

from app.schemas.health import HealthData
from app.schemas.response import Response, handle_success

router = APIRouter()


@router.get("/live", response_model=Response[HealthData], summary="Liveness probe")
async def liveness(request: Request):
    return handle_success(request, HealthData(status="ok"))


@router.get("/ready", response_model=Response[HealthData], summary="Readiness probe")
async def readiness(request: Request):
    return handle_success(request, HealthData(status="ok"))
