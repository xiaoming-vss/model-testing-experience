from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.sprint_code_overview import get_sprint_code_overview
from testing_agent.schemas.common import ApiResponse
from testing_agent.schemas.sprint_code_overview import SprintCodeOverviewResponse

router = APIRouter()

router.get(
    "/sprints/{sprint_id}/code-overview",
    response_model=ApiResponse[SprintCodeOverviewResponse],
)(get_sprint_code_overview)
