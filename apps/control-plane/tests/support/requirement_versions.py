"""Adopted requirement-understanding inputs for generation scenarios."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

ARTIFACT_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures/requirement_artifacts"


def material_artifact() -> dict:
    fixture = ARTIFACT_FIXTURES / "readable-material.example.json"
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


def adopt_material(
    client,
    requirement_id,
    *,
    headers,
    project_id=None,
    sprint_id=None,
    content=None,
):
    """Create and adopt material through the candidate workflow for API tests."""
    from uuid import uuid4

    from support.project_api import seed_requirement_source
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    artifact = (
        content if content is not None else json.dumps(material_artifact(), ensure_ascii=False)
    )

    async def find_project():
        async with client.app.state.test_sessions() as session:
            requirement = await session.scalar(
                select(Requirement).where(Requirement.requirement_id == requirement_id)
            )
            sprint = await session.scalar(
                select(Sprint).where(Sprint.sprint_id == (sprint_id or requirement.sprint_id))
            )
            return project_id or sprint.project_id

    project = asyncio.run(find_project())
    seed_requirement_source(client, requirement_id)
    connection = client.post(
        f"/v1/projects/{project}/integrations/llm/connections",
        headers=headers,
        json={
            "name": f"material-{uuid4()}",
            "baseUrl": "https://llm.example",
            "apiKey": "test",
            "modelId": "test",
        },
    )
    assert connection.status_code == 200, connection.text
    base = (
        f"/v1/requirements/{requirement_id}/generation/requirement_analysis/stages/extracting_text"
    )
    launched = client.post(
        base + "/candidate-run",
        headers=headers,
        json={"connectionId": connection.json()["data"]["connectionId"]},
    )
    assert launched.status_code == 200, launched.text
    run = launched.json()["data"]

    async def finish():
        async with client.app.state.test_sessions() as session:
            attempt = await session.get(AiGenerationAttempt, run["attemptId"])
            await StageWorkerTransitions(session).completed(
                attempt.stage_id,
                attempt.id,
                run["requestId"],
                content=artifact,
                output_format="json",
                output_context=None,
            )
            queue = await session.scalar(
                select(WorkerTask).where(WorkerTask.task_id == run["requestId"])
            )
            queue.status = "success"
            await session.commit()

    asyncio.run(finish())
    candidates = client.get(base + "/candidates", headers=headers).json()["data"]["items"]
    candidate = next(item for item in candidates if item["currentAttemptId"] == run["attemptId"])
    current = client.get(base + "/current", headers=headers).json()["data"]
    adopted = client.post(
        base + "/adoption",
        headers=headers,
        json={
            "action": "adopt",
            "candidateId": candidate["candidateId"],
            "expectedCandidateToken": candidate["candidateToken"],
            "expectedAttemptId": run["attemptId"],
            "expectedCurrentToken": current["currentToken"],
            "requestId": str(uuid4()),
        },
    )
    assert adopted.status_code == 200, adopted.text
    return candidate["candidateId"]
