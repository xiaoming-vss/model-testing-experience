"""Read candidate metadata and details within the requirement workspace."""

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.errors import success_payload
from testing_agent.schemas.generation_candidates import (
    CandidateDeriveRequest,
    CandidateDispositionRequest,
    CandidateEditRequest,
    CandidateRelationsRunRequest,
    CandidateUiSourceCheckRequest,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_candidate_commands import CandidateCommands
from testing_agent.services.generation_candidate_queries import CandidateQueries
from testing_agent.services.generation_candidate_relations import CandidateRelations
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_ui_source_check import UiCandidateSourceCheck


async def list_generation_candidates(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).list(requirement_id, kind, stage, user_id, page, page_size)
    )


async def get_generation_candidate(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    candidate_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).detail(requirement_id, kind, stage, candidate_id, user_id)
    )


async def check_ui_candidate_source(
    requirement_id: str,
    stage: str,
    candidate_id: str,
    body: CandidateUiSourceCheckRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await UiCandidateSourceCheck(service).check(
            requirement_id=requirement_id,
            stage=stage,
            candidate_id=candidate_id,
            request=body,
            actor_id=user_id,
        )
    )


async def get_current_candidate_relations(
    requirement_id: str,
    current_token: str = Query(..., alias="currentToken", min_length=1, max_length=64),
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateRelations(service, action="read").view(
            requirement_id=requirement_id, current_token=current_token, actor_id=user_id
        )
    )


async def run_current_candidate_relations(
    requirement_id: str,
    body: CandidateRelationsRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateRelations(service, action="execute").run(
            requirement_id=requirement_id,
            current_token=body.current_token,
            connection_id=body.connection_id,
            request_id=body.request_id,
            actor_id=user_id,
        )
    )


async def dispose_generation_candidate(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    candidate_id: str,
    body: CandidateDispositionRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateCommands(service).dispose(
            requirement_id, kind, stage, candidate_id, body, user_id
        )
    )


async def edit_generation_candidate(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    candidate_id: str,
    body: CandidateEditRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateCommands(service).edit(
            requirement_id, kind, stage, candidate_id, body, user_id
        )
    )


async def derive_generation_candidate(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    candidate_id: str,
    body: CandidateDeriveRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateCommands(service).derive(
            requirement_id, kind, stage, candidate_id, body, user_id
        )
    )
