from fastapi import Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from testing_agent.api.deps import get_current_user_id, get_integration_bug_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.integration_bug import IntegrationFieldsRequest, IntegrationSyncRequest


async def submit_sync(
    bug_id: str,
    body: IntegrationSyncRequest,
    user_id: str = Depends(get_current_user_id),
    service=Depends(get_integration_bug_service),
):
    result = await service.submit(user_id, bug_id, body, "zentao_bug_sync")
    return JSONResponse(status_code=202, content=jsonable_encoder(success_payload(result)))


async def submit_fields(
    bug_id: str,
    body: IntegrationFieldsRequest,
    user_id: str = Depends(get_current_user_id),
    service=Depends(get_integration_bug_service),
):
    result = await service.submit(user_id, bug_id, body, "zentao_bug_fields_update")
    return JSONResponse(status_code=202, content=jsonable_encoder(success_payload(result)))


async def get_job(
    bug_id: str,
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    service=Depends(get_integration_bug_service),
):
    return success_payload(await service.get(user_id, bug_id, job_id))
