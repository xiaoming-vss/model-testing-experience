from __future__ import annotations

from fastapi import APIRouter, Depends

from testing_agent.api.deps import verify_worker_token
from testing_agent.handlers.ui_run_variables import resolve_variables, write_variables
from testing_agent.schemas.ui_variables import (
    ResolveUiRunVariablesResponse,
    WriteUiRunVariablesResponse,
)

router = APIRouter(prefix="/ui-runs", dependencies=[Depends(verify_worker_token)])

router.post(
    "/{run_id}/variables:resolve",
    response_model=ResolveUiRunVariablesResponse,
)(resolve_variables)

router.post(
    "/{run_id}/variables:write",
    response_model=WriteUiRunVariablesResponse,
)(write_variables)
