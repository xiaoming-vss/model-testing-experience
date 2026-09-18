from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_sprint_daily_metrics_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.sprint_daily_metrics import SprintDailyMetricRequest
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


async def list_sprint_daily_metrics(
    sprint_id: str,
    start_date: str = Query(default="", alias="startDate"),
    end_date: str = Query(default="", alias="endDate"),
    user_id: str = Depends(get_current_user_id),
    service: SprintDailyMetricsService = Depends(get_sprint_daily_metrics_service),
):
    return success_payload(await service.list(sprint_id, user_id, start_date, end_date))


async def get_sprint_daily_metric(
    sprint_id: str,
    snapshot_date: str,
    user_id: str = Depends(get_current_user_id),
    service: SprintDailyMetricsService = Depends(get_sprint_daily_metrics_service),
):
    return success_payload(await service.get(sprint_id, snapshot_date, user_id))


async def upsert_sprint_daily_metric(
    sprint_id: str,
    snapshot_date: str,
    body: SprintDailyMetricRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: SprintDailyMetricsService = Depends(get_sprint_daily_metrics_service),
):
    payload = body.model_dump(by_alias=False, exclude_none=True) if body is not None else None
    return success_payload(await service.upsert(sprint_id, snapshot_date, payload, user_id))
