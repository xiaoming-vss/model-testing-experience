from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.sprint_daily_metrics import (
    get_sprint_daily_metric,
    list_sprint_daily_metrics,
    upsert_sprint_daily_metric,
)
from testing_agent.schemas.common import ApiResponse, ListResponse
from testing_agent.schemas.sprint_daily_metrics import SprintDailyMetricResponse

router = APIRouter()

router.get(
    "/sprints/{sprint_id}/daily-metrics",
    response_model=ApiResponse[ListResponse[SprintDailyMetricResponse]],
)(list_sprint_daily_metrics)
router.get(
    "/sprints/{sprint_id}/daily-metrics/{snapshot_date}",
    response_model=ApiResponse[SprintDailyMetricResponse],
)(get_sprint_daily_metric)
router.put(
    "/sprints/{sprint_id}/daily-metrics/{snapshot_date}",
    response_model=ApiResponse[SprintDailyMetricResponse],
)(upsert_sprint_daily_metric)
