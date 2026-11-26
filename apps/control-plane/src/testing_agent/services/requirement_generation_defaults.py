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


async def add_default_generation_tasks(
    session: AsyncSession, requirement: Requirement, project_id: str, user_id: str
) -> None:
    """Add default tasks, chains and empty stage content in one transaction.

    The models declare foreign keys but no ORM relationships, so SQLAlchemy does
    not order the inserts between mappers. Flush the foreign-key layers
    explicitly; otherwise a child table can be written before its parent and
    MySQL rejects the requirement creation.
    """
    tasks: list[tuple[str, str]] = []
    for kind, label in (("requirement_analysis", "需求分析"), ("function", "功能测试")):
        task_id = new_id()
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
        tasks.append((kind, task_id))
    # The caller has already added the requirement; persist it with the tasks
    # before anything references them.
    await session.flush()

    stages: list[tuple[str, str, str]] = []
    for kind, task_id in tasks:
        chain_id = uuid4().hex
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
            stages.append((stage_id, chain_id, name))
    await session.flush()

    for stage_id, chain_id, name in stages:
        session.add(
            AiGenerationStageContent(
                stage_id=stage_id,
                chain_id=chain_id,
                stage=name,
                content_token=uuid4().hex,
            )
        )
