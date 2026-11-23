"""Initialize a candidate chain for an unused configuration."""

# transaction-bound: lock the requirement, task, legacy state and new slots together.

from dataclasses import dataclass

from sqlalchemy import or_, select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import stage_names
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.repositories.generation_current_chain import (
    bind_current_chain,
    ensure_empty_slot,
)
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_chain import GenerationChainService


@dataclass(frozen=True)
class InitializedChain:
    chain_id: str
    task_id: str
    created: bool


class CandidateChainInitialization:
    """Bind a fresh configuration, or safely replay an existing binding.

    This internal boundary owns its request-scoped transaction. It never chooses
    among older configurations or invents conversion of their versions, drafts
    or attempts. Existing historical configurations are not reused.
    """

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="write")

    async def initialize(
        self, *, requirement_id: str, kind: DesignKind, task_id: str, actor_id: str
    ) -> InitializedChain:
        try:
            if not task_id:
                raise ErrBadRequest()
            names = stage_names(kind)
            parent = await self.scope.authorize(requirement_id, actor_id)
            await self.session.rollback()
            await self.scope.lock_scope(requirement_id, actor_id, parent)
            task_ids = list(
                (
                    await self.session.scalars(
                        select(AiGenerateTask.task_id)
                        .where(
                            AiGenerateTask.requirement_id == requirement_id,
                            AiGenerateTask.task_type == task_type_for(kind),
                        )
                        .order_by(AiGenerateTask.task_id)
                    )
                ).all()
            )
            tasks = []
            for identifier in task_ids:
                task = await self.chain.tasks.get_task_for_update(identifier)
                if (
                    task is None
                    or task.project_id != parent.project_id
                    or task.sprint_id not in ("", parent.sprint_id)
                ):
                    raise ErrBadRequest()
                await self.chain.access.validate_task_scope(task)
                tasks.append(task)
            if task_id not in task_ids:
                raise ErrBadRequest()
            existing = await self.session.scalar(
                select(RequirementGenerationChain)
                .where(
                    RequirementGenerationChain.requirement_id == requirement_id,
                    RequirementGenerationChain.kind == kind,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if existing is not None and existing.task_id != task_id:
                raise dynamic_error(ErrBadRequest, "该需求已有当前生成链")
            created = existing is None
            if created:
                if len(tasks) != 1:
                    raise dynamic_error(ErrBadRequest, "存在多个历史配置，请重新创建生成设置")
                legacy_attempt = await self.session.scalar(
                    select(AiGenerationAttempt.id)
                    .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                    .where(AiGenerationStage.task_id == task_id)
                    .limit(1)
                    .with_for_update()
                )
                legacy_stage = await self.session.scalar(
                    select(AiGenerationStage.id)
                    .where(
                        AiGenerationStage.task_id == task_id,
                        or_(
                            AiGenerationStage.current_attempt_id.is_not(None),
                            AiGenerationStage.active_attempt_id.is_not(None),
                            AiGenerationStage.review_status != "pending",
                        ),
                    )
                    .limit(1)
                    .with_for_update()
                )
                if legacy_attempt is not None or legacy_stage:
                    raise dynamic_error(ErrBadRequest, "存在历史生成数据，请重新创建生成设置")
            binding = await bind_current_chain(
                self.session, requirement_id=requirement_id, kind=kind, task_id=task_id
            )
            for name in names:
                stage, _ = await lock_or_create_stage(self.session, task_id, name)
                await ensure_empty_slot(self.session, chain_id=binding.chain_id, stage_id=stage.id)
            result = InitializedChain(binding.chain_id, task_id, created)
            await self.session.commit()
            return result
        except Exception:
            await self.session.rollback()
            raise
