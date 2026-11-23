"""Fresh chain initialization never silently converts historical data."""

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation import generation_services

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.generation_chain_initialization import CandidateChainInitialization


def application(sync):
    session = AsyncSessionAdapter(sync)
    return CandidateChainInitialization(
        generation_services(AiGenerateTaskRepository(session)).chain
    )


async def test_fresh_initialization_creates_one_chain_and_empty_slots(database):  # noqa: F811
    sync, _, _ = database
    app = application(sync)
    options = dict(requirement_id="req", kind="function", task_id="task")
    with pytest.raises(AppError) as denied:
        await app.initialize(**options, actor_id="other")
    assert denied.value.http_code == 403
    first = await app.initialize(**options, actor_id="u")
    second = await app.initialize(**options, actor_id="u")
    assert first.created and not second.created and first.chain_id == second.chain_id
    assert sync.query(RequirementGenerationChain).count() == 1
    slots = sync.query(AiGenerationStageContent).all()
    assert {slot.stage for slot in slots} == {
        "requirement_analysis",
        "case_names",
        "detailed_cases",
    }
    assert all(slot.source_candidate_id is None and slot.content_token for slot in slots)


async def test_history_and_multiple_configurations_require_conversion(database):  # noqa: F811
    sync, _, _ = database
    app = application(sync)
    options = dict(requirement_id="req", kind="function", task_id="task", actor_id="u")
    sync.add(AiGenerationStage(id="legacy-stage", task_id="task", stage="case_names"))
    sync.flush()
    sync.add(
        AiGenerationAttempt(
            id="old-attempt",
            stage_id="legacy-stage",
            attempt_no=1,
            operation="generate",
            status="failed",
        )
    )
    sync.commit()
    with pytest.raises(AppError, match="历史生成数据"):
        await app.initialize(**options)
    assert sync.query(RequirementGenerationChain).count() == 0
    sync.query(AiGenerationAttempt).delete()
    sync.query(AiGenerationStage).filter_by(id="legacy-stage").one().current_attempt_id = "old"
    sync.commit()
    with pytest.raises(AppError, match="历史生成数据"):
        await app.initialize(**options)
    sync.query(AiGenerationStage).filter_by(id="legacy-stage").one().current_attempt_id = None
    sync.add(
        AiGenerateTask(
            task_id="other-task",
            task_type="functional_case_generate",
            name="task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="",
        )
    )
    sync.commit()
    with pytest.raises(AppError, match="多个历史配置"):
        await app.initialize(**options)
    assert sync.query(RequirementGenerationChain).count() == 0
