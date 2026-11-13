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


def material_artifact() -> dict:
    fixture = UNDERSTANDING_FIXTURE.parent / "readable-material.example.json"
    return json.loads(fixture.read_text())


def scope_artifact(description: str = "保存后展示结果") -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactType": "test_scope_impact_risk",
        "testObjects": [
            {
                "id": "TO1",
                "sourceBlockIds": ["B1"],
                "basisStatus": "confirmed",
                "name": "保存结果",
                "type": "数据",
                "description": description,
            }
        ],
        "impactAreas": [],
        "risks": [],
        "openQuestions": [],
    }


def points_artifact() -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactType": "traceable_test_points",
        "reviewStatus": "self_review_only",
        "testPoints": [
            {
                "id": "TP1",
                "module": "保存",
                "dimension": "功能场景",
                "name": "【保存】验证保存后展示结果",
                "basis": "direct",
                "materialBlockIds": ["B1"],
                "testObjectIds": ["TO1"],
                "impactAreaIds": [],
                "riskIds": [],
                "materialQuestionIds": [],
                "scopeQuestionIds": [],
            }
        ],
        "coverageGaps": [],
    }


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


def material_version(session, requirement_id="r", version_no=1, content=None):
    if content is None:
        content = json.dumps(material_artifact(), ensure_ascii=False)
    version = understanding_version(session, requirement_id, version_no, content)
    version.stage = "extracting_text"
    version.artifact_format = "json"
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
    stage="feature_understanding",
):
    """Insert an approved feature_understanding version for API-level tests."""
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint

    task_id = f"understanding-{requirement_id}"
    artifact = (
        content
        if content is not None
        else json.dumps(
            material_artifact() if stage == "extracting_text" else understanding_artifact(),
            ensure_ascii=False,
        )
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
                    stage=stage,
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


def approve_material(client, requirement_id, **kwargs):
    return approve_understanding(client, requirement_id, stage="extracting_text", **kwargs)
