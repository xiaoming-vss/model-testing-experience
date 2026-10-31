from __future__ import annotations

from fastapi import Depends, Response

from testing_agent.api.deps import get_ui_run_variables_service
from testing_agent.schemas.ui_variables import (
    ResolveUiRunVariablesRequest,
    WriteUiRunVariablesRequest,
)
from testing_agent.services.ui_run_variables import UiRunVariablesService


async def resolve_variables(
    run_id: str,
    body: ResolveUiRunVariablesRequest,
    response: Response,
    service: UiRunVariablesService = Depends(get_ui_run_variables_service),
):
    response.headers["Cache-Control"] = "no-store"
    return await service.resolve(run_id, body)


async def write_variables(
    run_id: str,
    body: WriteUiRunVariablesRequest,
    response: Response,
    service: UiRunVariablesService = Depends(get_ui_run_variables_service),
):
    response.headers["Cache-Control"] = "no-store"
    return await service.write(run_id, body)
