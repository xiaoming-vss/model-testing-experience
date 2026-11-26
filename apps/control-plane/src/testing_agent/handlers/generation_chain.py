"""Requirement generation panorama and UI source options."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import success_payload
from testing_agent.schemas.generation_chain import (
    UiGenerationSourceCheck,
    UiGenerationSourceCheckRequest,
    UiGenerationSourceOptions,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_ui_source_check import UiCurrentSourceCheck


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
    options = await UiCurrentSourceCheck(service).options(requirement_id, user_id)
    return success_payload(UiGenerationSourceOptions.model_validate(options))


async def check_ui_generation_source(
    requirement_id: str,
    body: UiGenerationSourceCheckRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await UiCurrentSourceCheck(service).check(requirement_id, user_id, body)
    return success_payload(UiGenerationSourceCheck.model_validate(result))
