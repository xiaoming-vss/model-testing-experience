"""Candidate reads enforce requirement, stage and project access boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import sqlalchemy as sa
from support.project_api import account, api, project  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint

SOURCE_MANIFEST = {
    "generationMode": "trial",
    "lineageHash": "lineage-a",
    "sources": [
        {
            "requirementId": "candidate-req",
            "chainKind": "function",
            "stage": "requirement_analysis",
            "sourceKind": "candidate",
            "candidateId": "upstream-a",
            "snapshotId": "upstream-snapshot-a",
            "contentHash": "content-hash-a",
            "basisHash": "basis-hash-a",
        }
    ],
    "rootSources": [],
    "selectedSources": [
        {
            "chainKind": "function",
            "stage": "requirement_analysis",
            "sourceKind": "candidate",
            "candidateId": "upstream-a",
            "snapshotId": "upstream-snapshot-a",
        }
    ],
}


def seed_candidates(client, project_id, user_id):
    async def insert():
        async with client.app.state.test_sessions() as session:
            now = datetime.now(UTC)
            session.add(
                Sprint(
                    sprint_id="candidate-sprint",
                    project_id=project_id,
                    name="s",
                    start_time=now,
                    end_time=now + timedelta(days=1),
                )
            )
            await session.flush()
            session.add_all(
                [
                    Requirement(
                        requirement_id="candidate-req", sprint_id="candidate-sprint", name="r"
                    ),
                    Requirement(
                        requirement_id="candidate-other", sprint_id="candidate-sprint", name="other"
                    ),
                ]
            )
            await session.flush()
            session.add(
                AiGenerateTask(
                    task_id="candidate-task",
                    task_type="functional_case_generate",
                    name="task",
                    project_id=project_id,
                    sprint_id="candidate-sprint",
                    requirement_id="candidate-req",
                    creator_user_id=user_id,
                    source_type="requirement",
                    source_content="",
                )
            )
            await session.flush()
            session.add_all(
                [
                    RequirementGenerationChain(
                        chain_id="candidate-chain",
                        requirement_id="candidate-req",
                        kind="function",
                        task_id="candidate-task",
                    ),
                    AiGenerationStage(
                        id="candidate-stage", task_id="candidate-task", stage="case_names"
                    ),
                ]
            )
            await session.flush()
            for index, value in enumerate(("a", "b")):
                session.add(
                    AiGenerationCandidate(
                        candidate_id=value,
                        snapshot_id=f"snapshot-{value}",
                        chain_id="candidate-chain",
                        stage_id="candidate-stage",
                        content=f"private-{value}",
                        format="text",
                        context_json={"formatInfo": "test"},
                        candidate_token=f"token-{value}",
                        disposition="available",
                        generation_mode="trial",
                        created_by=user_id,
                        source_snapshot_json={"secret": "private-input"},
                        source_manifest_json=SOURCE_MANIFEST if value == "a" else None,
                        created_at=now + timedelta(seconds=index),
                    )
                )
            await session.flush()
            session.add(
                AiGenerationStageContent(
                    stage_id="candidate-stage",
                    chain_id="candidate-chain",
                    stage="case_names",
                    content="private-a",
                    content_token="slot-token",
                    source_candidate_id="a",
                    source_manifest_json=SOURCE_MANIFEST,
                )
            )
            await session.commit()

    asyncio.run(insert())


def test_candidate_listing_and_detail_are_scoped_and_bounded(api):  # noqa: F811
    user, owner = account(api, "candidate-owner")
    pid = project(api, owner)
    _, viewer = account(api, "candidate-viewer")
    _, outsider = account(api, "candidate-outsider")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "candidate-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    seed_candidates(api, pid, user["userId"])
    base = "/v1/requirements/candidate-req/generation/function/stages/case_names/candidates"

    response = api.get(base + "?page=1&pageSize=1", headers=viewer)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2 and data["items"][0]["candidateId"] == "b"
    assert "private-b" not in response.text and "private-input" not in response.text
    response = api.get(base + "?page=2&pageSize=1", headers=owner)
    assert response.json()["data"]["items"][0]["isCurrent"] is True
    detail = api.get(base + "/a", headers=viewer)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["content"] == "private-a"
    assert detail.json()["data"]["sourceTrace"] == [
        {
            "chainKind": "function",
            "stage": "requirement_analysis",
            "sourceKind": "candidate",
            "candidateId": "upstream-a",
            "snapshotId": "upstream-snapshot-a",
        }
    ]
    current = api.get(
        "/v1/requirements/candidate-req/generation/function/stages/case_names/current",
        headers=owner,
    )
    assert current.status_code == 200, current.text
    assert current.json()["data"]["sourceTrace"] == detail.json()["data"]["sourceTrace"]
    assert "private-input" not in detail.text
    assert "contextJson" not in detail.text
    assert api.get(base, headers=outsider).status_code == 403
    assert api.get(base + "/a", headers=outsider).status_code == 403
    assert api.get(base + "?pageSize=101", headers=owner).status_code == 400
    assert (
        api.get(base.replace("candidate-req", "candidate-other") + "/a", headers=owner).status_code
        == 404
    )
    assert (
        api.get(base.replace("case_names", "detailed_cases") + "/a", headers=owner).status_code
        == 404
    )


def test_candidate_rejection_is_scoped_idempotent_and_preserves_current(api):  # noqa: F811
    user, owner = account(api, "candidate-writer")
    pid = project(api, owner)
    _, viewer = account(api, "candidate-reader")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "candidate-reader", "role": "viewer"},
        ).status_code
        == 200
    )
    seed_candidates(api, pid, user["userId"])
    base = "/v1/requirements/candidate-req/generation/function/stages/case_names/candidates"
    request_id = str(uuid4())
    body = {
        "action": "reject",
        "expectedCandidateToken": "token-b",
        "requestId": request_id,
        "comment": "不采用",
    }
    assert api.post(base + "/b/disposition", headers=viewer, json=body).status_code == 403
    assert (
        api.post(
            base + "/a/disposition",
            headers=owner,
            json={
                "action": "reject",
                "expectedCandidateToken": "token-a",
                "requestId": str(uuid4()),
            },
        ).status_code
        == 400
    )
    first = api.post(base + "/b/disposition", headers=owner, json=body)
    assert first.status_code == 200, first.text
    result = first.json()["data"]
    assert result["candidateId"] == "b" and result["disposition"] == "rejected"
    assert result["candidateToken"] != "token-b"
    replay = api.post(base + "/b/disposition", headers=owner, json=body)
    assert replay.status_code == 200 and replay.json()["data"] == result
    assert (
        api.post(
            base + "/b/disposition", headers=owner, json={**body, "action": "discard"}
        ).status_code
        == 400
    )
    listing = api.get(base, headers=owner).json()["data"]["items"]
    rows = {item["candidateId"]: item for item in listing}
    assert rows["a"]["isCurrent"] and rows["a"]["disposition"] == "available"
    assert not rows["b"]["isCurrent"] and rows["b"]["disposition"] == "rejected"

    async def receipts():
        from sqlalchemy import select

        async with api.app.state.test_sessions() as session:
            return list((await session.scalars(select(AiGenerationReviewReceipt))).all())

    saved = asyncio.run(receipts())
    assert len(saved) == 1 and saved[0].comment == "不采用"
    assert saved[0].result_candidate_token == result["candidateToken"]


def test_edit_unreferenced_candidate_validates_and_never_replaces_current(api):  # noqa: F811
    user, owner = account(api, "candidate-editor")
    pid = project(api, owner)
    _, viewer = account(api, "candidate-edit-reader")
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "candidate-edit-reader", "role": "viewer"},
        ).status_code
        == 200
    )
    seed_candidates(api, pid, user["userId"])

    async def prepare():
        async with api.app.state.test_sessions() as session:
            task = await session.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == "candidate-task")
            )
            chain = await session.get(RequirementGenerationChain, "candidate-chain")
            stage = await session.get(AiGenerationStage, "candidate-stage")
            candidates = list((await session.scalars(sa.select(AiGenerationCandidate))).all())
            assert task and chain and stage
            task.task_type = "api_case_generate"
            chain.kind = "api"
            stage.stage = "interface_extract"
            slot = await session.get(AiGenerationStageContent, "candidate-stage")
            assert slot
            slot.stage = "interface_extract"
            session.add(
                AiGenerationAttempt(
                    id="edit-input",
                    stage_id="candidate-stage",
                    attempt_no=1,
                    operation="generate",
                    requested_by=user["userId"],
                    status="success",
                    output_content='{"interfaces": {}}',
                    output_format="json",
                    invalidated_reason="",
                )
            )
            for candidate in candidates:
                candidate.current_attempt_id = "edit-input"
                candidate.content = '{"interfaces": {}}'
                candidate.format = "json"
                candidate.source_snapshot_json = {"source": {}}
                candidate.context_json = {"moduleGeneration": {"sequence": 1}, "source": "keep"}
            await session.commit()

    asyncio.run(prepare())
    base = "/v1/requirements/candidate-req/generation/api/stages/interface_extract/candidates"
    body = {
        "expectedCandidateToken": "token-b",
        "expectedAttemptId": "edit-input",
        "content": '{"interfaces": {"login": {}}}',
    }
    assert api.put(base + "/b", headers=viewer, json=body).status_code == 403
    assert (
        api.put(
            base + "/a", headers=owner, json={**body, "expectedCandidateToken": "token-a"}
        ).status_code
        == 400
    )
    assert (
        api.put(base + "/b", headers=owner, json={**body, "content": "invalid json"}).status_code
        == 400
    )
    assert (
        api.put(
            base + "/b",
            headers=owner,
            json={**body, "content": '{"interfaces": {}, "interfaces": {"other": {}}}'},
        ).status_code
        == 400
    )
    response = api.put(base + "/b", headers=owner, json=body)
    assert response.status_code == 200, response.text
    edited = response.json()["data"]
    assert edited["candidateToken"] != "token-b" and edited["snapshotId"] != "snapshot-b"
    assert edited["currentAttemptId"] != "edit-input" and "login" in edited["content"]

    async def edited_attempt():
        async with api.app.state.test_sessions() as session:
            return await session.get(AiGenerationAttempt, edited["currentAttemptId"])

    attempt = asyncio.run(edited_attempt())
    assert attempt.operation == "edit" and attempt.execution_id is None
    assert not attempt.worker_task_id
    assert attempt.output_context_json == {"source": "keep"}
    assert api.put(base + "/b", headers=owner, json=body).status_code == 400
    listing = api.get(base, headers=owner).json()["data"]["items"]
    rows = {item["candidateId"]: item for item in listing}
    assert rows["a"]["isCurrent"] and not rows["b"]["isCurrent"]
    derive_body = {
        "expectedCandidateToken": "token-a",
        "expectedAttemptId": "edit-input",
        "content": '{"interfaces": {"derived": {}}}',
        "requestId": str(uuid4()),
    }
    assert api.post(base + "/a/derive", headers=viewer, json=derive_body).status_code == 403
    assert (
        api.post(
            base + "/a/derive", headers=owner, json={**derive_body, "content": "invalid"}
        ).status_code
        == 400
    )
    response = api.post(base + "/a/derive", headers=owner, json=derive_body)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    derived_id = result["candidateId"]
    assert derived_id not in {"a", "b"}
    detail = api.get(base + "/" + derived_id, headers=owner).json()["data"]
    assert detail["derivedFromCandidateId"] == "a" and not detail["isCurrent"]
    assert "derived" in detail["content"]
    assert (
        api.put(
            base + "/" + derived_id,
            headers=owner,
            json={
                "expectedCandidateToken": result["candidateToken"],
                "expectedAttemptId": detail["currentAttemptId"],
                "content": '{"interfaces": {"newer": {}}}',
            },
        ).status_code
        == 200
    )
    replay = api.post(base + "/a/derive", headers=owner, json=derive_body)
    assert replay.status_code == 200 and replay.json()["data"] == result
    newer = api.get(base + "/" + derived_id, headers=owner).json()["data"]
    assert "newer" in newer["content"] and newer["candidateToken"] != result["candidateToken"]
    current = api.get(base + "/a", headers=owner).json()["data"]
    assert current["isCurrent"] and current["frozenAt"] is not None
