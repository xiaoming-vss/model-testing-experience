"""Authorize long-lived test-run streams without holding a database session."""

from fastapi import HTTPException, Request

from testing_agent.core.errors import ErrForbidden
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.auth_session import SessionService
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


async def authorize_run_subscription(
    kind: str,
    run_id: str,
    user_id: str,
    api_cases: ApiCaseService,
    api_collections: ApiCollectionRunService,
    ui_runs: UiTestCaseRunService,
) -> None:
    """Check the current user may observe this run before subscribing to events."""
    if kind == "api-case":
        await api_cases.get_run(user_id, run_id)
        api_run = await api_cases.repository.get_run(run_id)
        if api_run is None or api_run.trigger_user_id != user_id:
            raise ErrForbidden()
    elif kind == "api-collection":
        await api_collections.get(user_id, run_id)
    elif kind == "ui-case":
        await ui_runs.get_case_run(user_id, run_id)
        ui_run = await ui_runs.repository.get_case_run(run_id)
        if ui_run is None or ui_run.trigger_user_id != user_id:
            raise ErrForbidden()
    else:
        await ui_runs.get_suite_run(user_id, run_id)


async def reauthorize_debug_stream(
    request: Request, user_id: str, domain: str, case_id: str
) -> None:
    """Recheck login, project and execute permission on a long-lived debug stream."""
    authorization = request.headers.get("authorization") or ""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401)
    async with AsyncSessionLocal() as session:
        actor = await SessionService(
            AuthSessionRepository(session), request.app.state.settings
        ).authenticate(token, method="POST", path=request.url.path)
        if actor != user_id:
            raise HTTPException(status_code=403)
        if domain == "api":
            await ApiCaseService(ApiCaseRepository(session)).get_accessible_context(
                actor, case_id, action="execute"
            )
        else:
            await UiTestCaseRunService(UiTestCaseRunRepository(session)).get_accessible_case(
                actor, case_id, action="execute"
            )
