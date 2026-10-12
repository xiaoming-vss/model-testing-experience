from fastapi import Depends, Query

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.requirement_design import (
    DesignKind,
    RequirementDesignConfigurationRequest,
    RequirementDesignRunRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.requirement_design import RequirementDesignService


async def get_requirement_design(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    tasks: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(await RequirementDesignService(tasks).overview(requirement_id, user_id))


async def list_requirement_design_runs(
    requirement_id: str,
    kind: DesignKind,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    pipeline_filter: str = Query(
        "all",
        alias="pipelineFilter",
        pattern="^(all|running|review_pending|approved|import_pending|imported|rejected|failed|canceled)$",
    ),
    user_id: str = Depends(get_current_user_id),
    tasks: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await RequirementDesignService(tasks).history(
            requirement_id,
            kind,
            user_id,
            page,
            page_size,
            pipeline_filter,
        )
    )


async def configure_requirement_design(
    requirement_id: str,
    kind: DesignKind,
    body: RequirementDesignConfigurationRequest,
    user_id: str = Depends(get_current_user_id),
    tasks: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await RequirementDesignService(tasks).configure(
            requirement_id,
            kind,
            body,
            user_id,
        )
    )


async def start_requirement_design(
    requirement_id: str,
    kind: DesignKind,
    body: RequirementDesignRunRequest,
    user_id: str = Depends(get_current_user_id),
    tasks: AiGenerateTaskService = Depends(get_ai_generate_task_service),
):
    return success_payload(
        await RequirementDesignService(tasks).start(
            requirement_id,
            kind,
            body,
            user_id,
        )
    )
