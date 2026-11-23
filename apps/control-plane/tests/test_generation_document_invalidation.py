"""Changing the requirement file marks dependent current content stale."""

from types import SimpleNamespace

from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_source_seed import seed_graph

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.schemas.requirement import UpdateRequirementRequest
from testing_agent.services.requirement import RequirementService


class SprintAccess:
    async def get_accessible_entity(self, user_id, sprint_id, *, action="read"):
        return SimpleNamespace(sprint_id=sprint_id, project_id="p")


class Files:
    async def attach(self, user_id, file_id, project_id, resource_type, resource_id, *, purpose):
        return SimpleNamespace(file_id=file_id, filename="new.docx", sha256="new-hash")


async def test_document_update_invalidates_only_document_consumers(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type = "docx"
    requirement.document_file_id = "old"
    requirement.document_filename = "old.docx"
    requirement.document_hash = "old-hash"
    for key in ("m", "a"):
        candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id=key).one()
        sync.add(
            AiGenerationStageContent(
                stage_id=candidate.stage_id,
                chain_id=candidate.chain_id,
                stage=graph[key].stage,
                content=candidate.content,
                format=candidate.format,
                source_candidate_id=key,
                content_token=f"token-{key}",
            )
        )
    for kind, task_type, stage_name in (
        ("api", "api_case_generate", "generate"),
        ("repository_profile", "repository_profile", "generate"),
    ):
        task_id, stage_id = f"task-{kind}", f"stage-{kind}"
        sync.add(
            AiGenerateTask(
                task_id=task_id,
                task_type=task_type,
                name=kind,
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                creator_user_id="u",
                source_type="text",
                source_content="",
            )
        )
        sync.flush()
        sync.add_all(
            [
                RequirementGenerationChain(
                    chain_id=f"chain-{kind}", requirement_id="req", kind=kind, task_id=task_id
                ),
                AiGenerationStage(id=stage_id, task_id=task_id, stage=stage_name),
            ]
        )
        sync.flush()
        sync.add(
            AiGenerationCandidate(
                candidate_id=f"candidate-{kind}",
                snapshot_id=f"snapshot-{kind}",
                chain_id=f"chain-{kind}",
                stage_id=stage_id,
                content="body",
                format="text",
                candidate_token=f"candidate-token-{kind}",
                disposition="available",
                generation_mode="current",
                created_by="u",
            )
        )
        sync.flush()
        sync.add(
            AiGenerationStageContent(
                stage_id=stage_id,
                chain_id=f"chain-{kind}",
                stage=stage_name,
                content="body",
                format="text",
                source_candidate_id=f"candidate-{kind}",
                content_token=f"token-{kind}",
            )
        )
    sync.commit()
    session = AsyncSessionAdapter(sync)
    service = RequirementService(RequirementRepository(session), SprintAccess(), files=Files())
    await service.update("u", "req", UpdateRequirementRequest(documentFileId="new"))
    slots = {item.stage_id: item for item in sync.query(AiGenerationStageContent).all()}
    for stage_id, previous_token in (
        ("stage-m", "token-m"),
        ("stage-a", "token-a"),
        ("stage-repository_profile", "token-repository_profile"),
    ):
        assert slots[stage_id].invalidated_at is not None
        assert slots[stage_id].content_token != previous_token
        assert slots[stage_id].content and slots[stage_id].source_candidate_id
    assert slots["stage-api"].invalidated_at is None
    assert slots["stage-api"].content_token == "token-api"
    tokens = {stage_id: slot.content_token for stage_id, slot in slots.items()}
    await service.update("u", "req", UpdateRequirementRequest(name="renamed"))
    await service.update("u", "req", UpdateRequirementRequest(documentFileId="new"))
    assert {
        item.stage_id: item.content_token for item in sync.query(AiGenerationStageContent)
    } == tokens
