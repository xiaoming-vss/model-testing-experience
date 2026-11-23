"""Requirement generation panorama and UI source options."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import ErrBadRequest, dynamic_error, success_payload
from testing_agent.schemas.generation_chain import (
    UiGenerationSourceCheck,
    UiGenerationSourceCheckRequest,
    UiGenerationSourceOptions,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_chain import GenerationChainService


async def get_generation_chains(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.overview(requirement_id, user_id))


async def get_generation_chain_view(
    requirement_id: str,
    kind: DesignKind,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.chain_view(requirement_id, kind, user_id, detail=True))


async def get_ui_generation_source_options(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    await service.scope(requirement_id, user_id)
    if service.ui_sources is None:
        raise dynamic_error(ErrBadRequest, "UI 仓库源码解析未配置")
    from testing_agent.services.repository_profile_current import RepositoryProfileCurrent

    current = await RepositoryProfileCurrent(service).read(
        requirement_id=requirement_id, actor_id=user_id
    )
    options = service.ui_sources.current_options(current)
    return success_payload(UiGenerationSourceOptions.model_validate(options))


async def check_ui_generation_source(
    requirement_id: str,
    body: UiGenerationSourceCheckRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    await service.scope(requirement_id, user_id)
    if service.ui_sources is None:
        raise dynamic_error(ErrBadRequest, "UI 仓库源码解析未配置")
    task = await service.tasks.get_requirement(requirement_id)
    if task is None:
        raise ErrBadRequest()
    sprint = await service.tasks.get_sprint(task.sprint_id)
    if sprint is None:
        raise ErrBadRequest()
    project_id = sprint.project_id
    from testing_agent.services.generation_source_errors import source_error
    from testing_agent.services.repository_profile_current import RepositoryProfileCurrent

    reader = RepositoryProfileCurrent(service)
    current = await reader.read(requirement_id=requirement_id, actor_id=user_id)
    if current is None or current.candidate_id != body.profile_candidate_id:
        raise source_error("source_mismatch")
    result = await service.ui_sources.check_current(
        current=current,
        project_id=project_id,
        user_id=user_id,
        repository_id=body.repository_id,
        pinned_commit=body.pinned_commit,
        gitlab_connection_id=body.gitlab_connection_id,
    )
    verified = await reader.read(requirement_id=requirement_id, actor_id=user_id)
    if verified is None or (
        verified.candidate_id,
        verified.snapshot_id,
        verified.current_token,
    ) != (current.candidate_id, current.snapshot_id, current.current_token):
        raise source_error("concurrent_change")
    return success_payload(UiGenerationSourceCheck.model_validate(result))
