"""Requirement generation panorama and stage version actions."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import ErrBadRequest, dynamic_error, success_payload
from testing_agent.schemas.generation_chain import (
    GenerationChainImportRequest,
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
    GenerationChainSaveDraftRequest,
    UiGenerationSourceCheck,
    UiGenerationSourceCheckRequest,
    UiGenerationSourceOptions,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.stage_storage.chain_view import build_chain_view
from testing_agent.services.stage_storage.commands import DirectStageCommands
from testing_agent.services.stage_storage.version_delete import delete_stage_version
from testing_agent.services.stage_storage.version_views import version_detail


async def get_generation_chains(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    from typing import cast

    from testing_agent.domain.generation_chain import CHAIN_KINDS
    from testing_agent.schemas.generation_chain import GenerationChainOverview

    await service.scope(requirement_id, user_id)
    chains = []
    for item in CHAIN_KINDS:
        kind = cast(DesignKind, item)
        task = await service.repository.task(requirement_id, kind)
        if task is not None:
            if task.requirement_id != requirement_id:
                from testing_agent.core.errors import ErrNotFound

                raise ErrNotFound()
            await service.access.validate_task_scope(task)
        chains.append(
            await build_chain_view(service.tasks.session, requirement_id, kind, task, detail=False)
        )
    return success_payload(GenerationChainOverview(chains=chains))


async def get_generation_chain_view(
    requirement_id: str,
    kind: DesignKind,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    task = await service.optional_task(requirement_id, kind, user_id)
    return success_payload(
        await build_chain_view(service.tasks.session, requirement_id, kind, task, detail=True)
    )


async def get_ui_generation_source_options(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    await service.scope(requirement_id, user_id)
    if service.ui_sources is None:
        raise dynamic_error(ErrBadRequest, "UI 仓库源码解析未配置")
    options = await service.ui_sources.options(requirement_id)
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
    result = await service.ui_sources.check(
        requirement_id=requirement_id,
        project_id=sprint.project_id,
        user_id=user_id,
        profile_version_id=body.profile_version_id,
        repository_id=body.repository_id,
        pinned_commit=body.pinned_commit,
        gitlab_connection_id=body.gitlab_connection_id,
    )
    return success_payload(UiGenerationSourceCheck.model_validate(result))


async def get_generation_chain_version(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    task = await service.task(requirement_id, kind, user_id)
    return success_payload(await version_detail(service.tasks.session, task, kind, version_id))


async def get_generation_chain_import_options(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.import_options(requirement_id, kind, version_id, user_id))


async def import_generation_chain_version(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    body: GenerationChainImportRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await service.import_version(requirement_id, kind, version_id, body, user_id)
    )


async def run_generation_chain_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await DirectStageCommands(service).run(requirement_id, kind, stage, body, user_id)
    )


async def revise_generation_chain_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainRevisionRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await DirectStageCommands(service).revise(requirement_id, kind, stage, body, user_id)
    )


async def review_generation_chain_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    if not body.expected_attempt_id:
        raise dynamic_error(ErrBadRequest, "请刷新页面后重新审核当前候选")
    return success_payload(
        await DirectStageCommands(service).review(requirement_id, kind, stage, body, user_id)
    )


async def save_generation_chain_stage_draft(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainSaveDraftRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await DirectStageCommands(service).save(requirement_id, kind, stage, body, user_id)
    )


async def delete_generation_chain_version(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    from testing_agent.schemas.generation_chain import GenerationChainDeleteVersionResponse

    task = await service.task(requirement_id, kind, user_id, action="write", lock=True)
    invalidated = await delete_stage_version(service.tasks.session, task, version_id)
    await service.tasks.session.commit()
    return success_payload(
        GenerationChainDeleteVersionResponse(
            version_id=version_id, deleted=True, invalidated_draft_count=invalidated
        )
    )
