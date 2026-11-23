"""Default generation tasks created atomically with a new requirement."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import stage_names
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement


def add_default_generation_tasks(
    session: AsyncSession, requirement: Requirement, project_id: str, user_id: str
) -> None:
    for kind, label in (("requirement_analysis", "需求分析"), ("function", "功能测试")):
        task_id, chain_id = new_id(), uuid4().hex
        session.add(
            AiGenerateTask(
                task_id=task_id,
                task_type=task_type_for(kind),
                name=f"{requirement.name[: 117 - len(label)]} · {label}",
                project_id=project_id,
                sprint_id=requirement.sprint_id,
                requirement_id=requirement.requirement_id,
                creator_user_id=user_id,
                source_type=(
                    requirement.document_type if kind == "requirement_analysis" else "requirement"
                ),
                source_content=(
                    (requirement.document_content or "") if kind == "requirement_analysis" else ""
                ),
                instruction="",
            )
        )
        session.add(
            RequirementGenerationChain(
                chain_id=chain_id,
                requirement_id=requirement.requirement_id,
                kind=kind,
                task_id=task_id,
            )
        )
        for name in stage_names(kind):
            stage_id = new_id()
            session.add(AiGenerationStage(id=stage_id, task_id=task_id, stage=name))
            session.add(
                AiGenerationStageContent(
                    stage_id=stage_id,
                    chain_id=chain_id,
                    stage=name,
                    content_token=uuid4().hex,
                )
            )
