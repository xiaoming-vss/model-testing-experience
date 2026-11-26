"""HTTP adapters for API/UI run streams, stop requests and live-debug submission."""

from fastapi import Depends, Request
from fastapi.responses import StreamingResponse

from testing_agent.api.deps import get_current_user_id, get_test_run_stream_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.schemas.test_run import RunKind
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest
from testing_agent.services.test_run_stream import TestRunStreamService


async def api_debug_stream(
    case_id: str,
    body: RunApiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: TestRunStreamService = Depends(get_test_run_stream_service),
) -> StreamingResponse:
    return await service.start_api_debug(request, case_id, body, user_id)


async def ui_debug_stream(
    case_id: str,
    body: DebugRunUiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: TestRunStreamService = Depends(get_test_run_stream_service),
) -> StreamingResponse:
    return await service.start_ui_debug(request, case_id, body, user_id)


async def test_run_events(
    kind: RunKind,
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    service: TestRunStreamService = Depends(get_test_run_stream_service),
) -> StreamingResponse:
    return await service.stream(kind, run_id, request, user_id)


async def stop_test_run(
    kind: RunKind,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestRunStreamService = Depends(get_test_run_stream_service),
):
    return success_payload(await service.stop(kind, run_id, user_id))
