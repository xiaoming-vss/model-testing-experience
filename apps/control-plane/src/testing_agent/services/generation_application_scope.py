"""Shared permission and parent-lock boundary for generation operations."""

# transaction-bound: project, sprint, requirement and bound tasks lock in order.

from dataclasses import dataclass

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.project_policy import ProjectAction
from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.repositories.generation_schema import candidate_schema_installed
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.project_access import require_project_access


@dataclass(frozen=True)
class GenerationParentIdentity:
    sprint_id: str
    project_id: str


class GenerationApplicationScope:
    """Authorize and recheck stable parent identities under ordered locks."""

    def __init__(self, chain: GenerationChainService, *, action: ProjectAction) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.action = action

    async def authorize(self, requirement_id: str, actor_id: str) -> GenerationParentIdentity:
        requirement = await self.chain.scope(requirement_id, actor_id)
        sprint = await self.chain.tasks.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        project = await self.chain.tasks.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.session, actor_id, project, self.action)
        if not await candidate_schema_installed(self.session):
            raise dynamic_error(ErrBadRequest, "候选数据表尚未安装，请先完成数据库升级")
        return GenerationParentIdentity(sprint.sprint_id, sprint.project_id)

    async def lock_scope(
        self, requirement_id: str, actor_id: str, parent: GenerationParentIdentity
    ) -> None:
        await self.chain.access.ensure_project_access(
            actor_id, parent.project_id, action=self.action
        )
        sprint = await self.chain.tasks.get_sprint_for_update(parent.sprint_id)
        if sprint is None or sprint.project_id != parent.project_id:
            raise ErrNotFound()
        requirement = await self.chain.tasks.get_requirement_for_update(requirement_id)
        if requirement is None or requirement.sprint_id != parent.sprint_id:
            raise ErrNotFound()

    async def lock_parents(
        self, requirement_id: str, actor_id: str, parent: GenerationParentIdentity
    ) -> None:
        await self.lock_scope(requirement_id, actor_id, parent)
        rows = (
            await self.session.execute(
                select(RequirementGenerationChain.task_id, RequirementGenerationChain.kind)
                .where(RequirementGenerationChain.requirement_id == requirement_id)
                .order_by(RequirementGenerationChain.task_id)
            )
        ).all()
        for task_id, chain_kind in rows:
            try:
                expected_type = task_type_for(chain_kind)
            except KeyError as exc:
                raise ErrNotFound() from exc
            task = await self.chain.tasks.get_task_for_update(task_id)
            if (
                task is None
                or task.requirement_id != requirement_id
                or task.project_id != parent.project_id
                or task.sprint_id not in ("", parent.sprint_id)
                or task.task_type != expected_type
            ):
                raise ErrNotFound()
            await self.chain.access.validate_task_scope(task)
