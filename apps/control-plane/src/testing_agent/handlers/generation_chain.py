"""Requirement generation panorama and stage version actions."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import success_payload
from testing_agent.schemas.generation_chain import (
    GenerationChainImportRequest,
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
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
    return success_payload(await service.chain(requirement_id, kind, user_id))


async def get_generation_chain_version(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.version(requirement_id, kind, version_id, user_id))


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
    return success_payload(await service.run_stage(requirement_id, kind, stage, body, user_id))


async def revise_generation_chain_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainRevisionRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.revise_stage(requirement_id, kind, stage, body, user_id))


async def review_generation_chain_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: GenerationChainReviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.review_stage(requirement_id, kind, stage, body, user_id))


async def delete_generation_chain_version(
    requirement_id: str,
    kind: DesignKind,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(await service.delete_version(requirement_id, kind, version_id, user_id))
