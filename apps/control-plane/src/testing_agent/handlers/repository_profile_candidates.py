"""Requirement-scoped profile candidate and current-result adapters."""

from dataclasses import asdict

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import success_payload
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateDispositionRequest,
    CurrentClearRequest,
)
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication
from testing_agent.services.generation_candidate_commands import CandidateCommands
from testing_agent.services.generation_candidate_queries import CandidateQueries
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.repository_profile_adoption import (
    PROFILE_KIND,
    PROFILE_STAGE,
    RepositoryProfileAdoption,
)


async def list_profile_candidates(
    requirement_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).list(
            requirement_id, PROFILE_KIND, PROFILE_STAGE, user_id, page, page_size
        )
    )


async def get_profile_candidate(
    requirement_id: str,
    candidate_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).detail(
            requirement_id, PROFILE_KIND, PROFILE_STAGE, candidate_id, user_id
        )
    )


async def get_current_profile(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).current(
            requirement_id, PROFILE_KIND, PROFILE_STAGE, user_id
        )
    )


async def adopt_profile_candidate(
    requirement_id: str,
    body: CandidateAdoptRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await RepositoryProfileAdoption(service).adopt(
        requirement_id=requirement_id, request=body, actor_id=user_id
    )
    return success_payload(asdict(result))


async def clear_current_profile(
    requirement_id: str,
    body: CurrentClearRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await CandidateAdoptionApplication(service).clear(
        requirement_id=requirement_id,
        kind=PROFILE_KIND,
        stage=PROFILE_STAGE,
        request=body,
        actor_id=user_id,
    )
    return success_payload(asdict(result))


async def dispose_profile_candidate(
    requirement_id: str,
    candidate_id: str,
    body: CandidateDispositionRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateCommands(service).dispose(
            requirement_id, PROFILE_KIND, PROFILE_STAGE, candidate_id, body, user_id
        )
    )
