"""Approved requirement-understanding inputs for generation scenarios."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask

UNDERSTANDING_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures/requirement_artifacts/requirement-understanding.example.json"
)


def understanding_artifact() -> dict:
    return json.loads(UNDERSTANDING_FIXTURE.read_text())


def understanding_version(session, requirement_id="r", version_no=1, content="versioned source"):
    task_id = f"understanding-{requirement_id}"
    task = session.query(AiGenerateTask).filter_by(task_id=task_id).first()
    if task is None:
        task = AiGenerateTask(
            task_id=task_id,
            task_type="requirement_analysis",
            name="需求分析",
            project_id="p",
            sprint_id="s",
            requirement_id=requirement_id,
            creator_user_id="u",
            source_type="requirement",
            source_content="",
        )
        session.add(task)
        session.flush()
    version = AiGenerateStageVersion(
        version_id=f"understanding-{requirement_id}-v{version_no}",
        task_id=task_id,
        stage="feature_understanding",
        version_no=version_no,
        attempt_id=f"understanding-attempt-{requirement_id}-{version_no}",
        artifact_content=content,
        artifact_format="text",
        reviewer_user_id="u",
        upstream_versions_json={},
    )
    session.add(version)
    session.commit()
    return version


def approve_understanding(
    client,
    requirement_id,
    *,
    project_id=None,
    sprint_id=None,
    content=None,
    version_no=1,
):
    """Insert an approved feature_understanding version for API-level tests."""
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint

    task_id = f"understanding-{requirement_id}"
    artifact = (
        content if content is not None else json.dumps(understanding_artifact(), ensure_ascii=False)
    )

    async def insert():
        async with client.app.state.test_sessions() as session:
            project, sprint = project_id, sprint_id
            if project is None or sprint is None:
                requirement = await session.scalar(
                    select(Requirement).where(Requirement.requirement_id == requirement_id)
                )
                sprint = sprint or requirement.sprint_id
                resolved = await session.scalar(select(Sprint).where(Sprint.sprint_id == sprint))
                project = project or resolved.project_id
            task = await session.scalar(
                select(AiGenerateTask).where(AiGenerateTask.task_id == task_id)
            )
            if task is None:
                task = AiGenerateTask(
                    task_id=task_id,
                    task_type="requirement_analysis",
                    name="需求分析",
                    project_id=project,
                    sprint_id=sprint,
                    requirement_id=requirement_id,
                    creator_user_id="u",
                    source_type="requirement",
                    source_content="",
                )
                session.add(task)
                await session.flush()
            session.add(
                AiGenerateStageVersion(
                    version_id=f"understanding-{requirement_id}-v{version_no}",
                    task_id=task_id,
                    stage="feature_understanding",
                    version_no=version_no,
                    attempt_id=f"understanding-attempt-{requirement_id}-{version_no}",
                    artifact_content=artifact,
                    artifact_format="json",
                    reviewer_user_id="u",
                    upstream_versions_json={},
                )
            )
            await session.commit()

    asyncio.run(insert())
    return f"understanding-{requirement_id}-v{version_no}"
