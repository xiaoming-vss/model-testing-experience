"""Transaction-scoped binding and empty slots for requirement generation chains.

The caller must authorize the user and lock the project and sprint before
calling these primitives; slot allocation also requires the task lock. They do
not commit or choose between legacy tasks.
"""

from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import stage_names
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.requirement_design import requirement_scope
from testing_agent.schemas.requirement_design import DesignKind


class ChainBindingConflict(ValueError):
    """A chain, task or stage does not belong to the requested scope."""


async def bind_current_chain(
    session: AsyncSession, *, requirement_id: str, kind: DesignKind, task_id: str
) -> RequirementGenerationChain:
    """Bind one validated task under the requirement lock; leave commit to caller."""
    requirement = await session.scalar(
        select(Requirement)
        .where(Requirement.requirement_id == requirement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if requirement is None:
        raise ChainBindingConflict("requirement not found")
    task = await session.scalar(
        select(AiGenerateTask)
        .where(
            AiGenerateTask.task_id == task_id,
            AiGenerateTask.task_type == task_type_for(kind),
            *requirement_scope(requirement_id),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise ChainBindingConflict("task does not belong to requirement and kind")
    existing = await session.scalar(
        select(RequirementGenerationChain)
        .where(
            RequirementGenerationChain.requirement_id == requirement_id,
            RequirementGenerationChain.kind == kind,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.task_id != task_id:
            raise ChainBindingConflict("chain is already bound to another task")
        return existing
    chain = RequirementGenerationChain(
        chain_id=uuid4().hex, requirement_id=requirement_id, kind=kind, task_id=task_id
    )
    session.add(chain)
    await session.flush()
    return chain


async def ensure_empty_slot(
    session: AsyncSession, *, chain_id: str, stage_id: str
) -> AiGenerationStageContent:
    """Get or allocate a persistent stage slot with a fresh empty-state token.

    A nonempty slot is returned unchanged. The stage lock serializes creation
    and preserves the existing worker-to-stage lock order.
    """
    stage = await session.scalar(
        select(AiGenerationStage)
        .where(AiGenerationStage.id == stage_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    chain = await session.scalar(
        select(RequirementGenerationChain)
        .where(RequirementGenerationChain.chain_id == chain_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if chain is None or stage is None or stage.task_id != chain.task_id:
        raise ChainBindingConflict("stage does not belong to chain")
    try:
        valid = stage.stage in stage_names(chain.kind)
    except KeyError:
        valid = False
    if not valid:
        raise ChainBindingConflict("stage does not belong to chain kind")
    task_id = await session.scalar(
        select(AiGenerateTask.task_id).where(
            AiGenerateTask.task_id == chain.task_id,
            AiGenerateTask.task_type == task_type_for(chain.kind),
            *requirement_scope(chain.requirement_id),
        )
    )
    if task_id is None:
        raise ChainBindingConflict("chain task does not belong to requirement and kind")
    existing = await session.scalar(
        select(AiGenerationStageContent)
        .where(AiGenerationStageContent.stage_id == stage_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.chain_id != chain_id or existing.stage != stage.stage:
            raise ChainBindingConflict("slot is bound to a different chain or stage")
        return existing
    slot = AiGenerationStageContent(
        stage_id=stage.id, chain_id=chain_id, stage=stage.stage, content_token=uuid4().hex
    )
    session.add(slot)
    await session.flush()
    return slot


async def delete_chain_storage_for_task(session: AsyncSession, *, task_id: str) -> None:
    """Delete a task's owned candidate storage; caller owns the deletion transaction.

    This is not attached to the legacy task-deletion path until the schema has
    been converted. Cross-chain derivations are left to fail closed via the FK.
    """
    chain_ids = list(
        await session.scalars(
            select(RequirementGenerationChain.chain_id)
            .where(RequirementGenerationChain.task_id == task_id)
            .with_for_update()
        )
    )
    if not chain_ids:
        return
    await session.execute(
        delete(AiGenerationStageContent).where(AiGenerationStageContent.chain_id.in_(chain_ids))
    )
    await session.execute(
        update(AiGenerationCandidate)
        .where(AiGenerationCandidate.chain_id.in_(chain_ids))
        .values(derived_from_candidate_id=None)
    )
    await session.execute(
        delete(AiGenerationCandidate).where(AiGenerationCandidate.chain_id.in_(chain_ids))
    )
    await session.execute(
        delete(RequirementGenerationChain).where(RequirementGenerationChain.chain_id.in_(chain_ids))
    )
