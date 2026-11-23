"""Request adapters for candidate generation, adoption and current imports."""

from dataclasses import asdict

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_chain
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import success_payload
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateChainInitializeRequest,
    CandidateRevisionRequest,
    CandidateRunRequest,
    CurrentImportPreviewRequest,
    CurrentImportRequest,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication
from testing_agent.services.generation_candidate_queries import CandidateQueries
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_chain_initialization import CandidateChainInitialization
from testing_agent.services.generation_dispatch_application import CandidateDispatchApplication
from testing_agent.services.generation_import_application import CurrentImportApplication
from testing_agent.services.generation_revision_application import CandidateRevisionApplication


async def initialize_candidate_chain(
    requirement_id: str,
    kind: DesignKind,
    body: CandidateChainInitializeRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await CandidateChainInitialization(service).initialize(
        requirement_id=requirement_id, kind=kind, task_id=body.task_id, actor_id=user_id
    )
    return success_payload(asdict(result))


async def get_current_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateQueries(service).current(requirement_id, kind, stage, user_id)
    )


async def run_candidate_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: CandidateRunRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await CandidateDispatchApplication(service).run(
        requirement_id=requirement_id, kind=kind, stage=stage, request=body, actor_id=user_id
    )
    return success_payload(asdict(result))


async def revise_candidate_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    candidate_id: str,
    body: CandidateRevisionRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await CandidateRevisionApplication(service).run(
        requirement_id=requirement_id,
        kind=kind,
        stage=stage,
        candidate_id=candidate_id,
        request=body,
        actor_id=user_id,
    )
    return success_payload(asdict(result))


async def preview_candidate_adoption(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: CandidateAdoptRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    return success_payload(
        await CandidateAdoptionApplication(service).preview(
            requirement_id=requirement_id, kind=kind, stage=stage, request=body, actor_id=user_id
        )
    )


async def adopt_candidate(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: CandidateAdoptRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
):
    result = await CandidateAdoptionApplication(service).adopt(
        requirement_id=requirement_id, kind=kind, stage=stage, request=body, actor_id=user_id
    )
    return success_payload(asdict(result))


async def preview_current_import(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: CurrentImportPreviewRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
    settings: Settings = Depends(get_settings),
):
    result = await CurrentImportApplication(service, secret=settings.jwt_key).preview(
        requirement_id=requirement_id,
        kind=kind,
        stage=stage,
        current_token=body.expected_current_token,
        target_id=body.target_id,
        actor_id=user_id,
    )
    return success_payload(asdict(result))


async def import_current_stage(
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    body: CurrentImportRequest,
    user_id: str = Depends(get_current_user_id),
    service: GenerationChainService = Depends(get_generation_chain),
    settings: Settings = Depends(get_settings),
):
    return success_payload(
        await CurrentImportApplication(service, secret=settings.jwt_key).execute(
            requirement_id=requirement_id,
            kind=kind,
            stage=stage,
            request=body,
            actor_id=user_id,
        )
    )
