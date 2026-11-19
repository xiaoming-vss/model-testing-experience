"""Start a single-case debug run after subscribing to its event stream."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from testing_agent.api.deps import (
    get_api_case_service,
    get_current_user_id,
    get_session,
    get_ui_test_case_run_service,
)
from testing_agent.core.sid import new_id
from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.live_debug_stream import start_debug_stream
from testing_agent.services.test_run_stream import reauthorize_debug_stream
from testing_agent.services.ui_test_case_run import UiTestCaseRunService

router = APIRouter()


@router.post("/test-debug-stream/api-case/{case_id}", response_class=StreamingResponse)
async def api_debug_stream(
    case_id: str,
    body: RunApiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    service: ApiCaseService = Depends(get_api_case_service),
):
    run_id = new_id()
    return await start_debug_stream(
        request,
        "api",
        run_id,
        lambda: service.run(user_id, case_id, body, run_id=run_id, live_debug=True),
        session,
        lambda: reauthorize_debug_stream(request, user_id, "api", case_id),
    )


@router.post("/test-debug-stream/ui-case/{case_id}", response_class=StreamingResponse)
async def ui_debug_stream(
    case_id: str,
    body: DebugRunUiCaseRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    service: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    run_id = new_id()
    return await start_debug_stream(
        request,
        "ui",
        run_id,
        lambda: service.debug_run_case(user_id, case_id, body, run_id=run_id, live_debug=True),
        session,
        lambda: reauthorize_debug_stream(request, user_id, "ui", case_id),
    )
