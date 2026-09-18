from __future__ import annotations

import json

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_sprint_code_overview_service
from testing_agent.core.errors import ErrBadRequest, success_payload
from testing_agent.services.sprint_code_overview import SprintCodeOverviewService


async def get_sprint_code_overview(
    sprint_id: str,
    connection_ids: str = Query(default="{}", alias="connectionIds"),
    user_id: str = Depends(get_current_user_id),
    service: SprintCodeOverviewService = Depends(get_sprint_code_overview_service),
):
    try:
        choices = json.loads(connection_ids)
        if not isinstance(choices, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in choices.items()
        ):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ErrBadRequest from exc
    return success_payload(await service.get_overview(user_id, sprint_id, choices))
