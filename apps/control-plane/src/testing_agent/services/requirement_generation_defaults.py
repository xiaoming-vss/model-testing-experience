"""Default generation tasks created atomically with a new requirement."""

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.requirement import Requirement


def add_default_generation_tasks(
    session: AsyncSession, requirement: Requirement, project_id: str, user_id: str
) -> None:
    for kind, label in (("requirement_analysis", "需求分析"), ("function", "功能测试")):
        session.add(
            AiGenerateTask(
                task_id=new_id(),
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
