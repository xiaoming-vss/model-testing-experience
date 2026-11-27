"""Exercise the history stage through its user and Worker HTTP entry points."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.pool import NullPool
from support.mysql_initialization import async_sessions, mysql  # noqa: F401
from support.project_api import (  # noqa: F401
    account,
    api,
    project,
    requirement,
    seed_llm_connection,
)
from support.requirement_versions import adopt_material, material_artifact

from testing_agent.api.deps import verify_worker_token
from testing_agent.db.session import get_session
from testing_agent.domain.generation_chain import (
    HISTORICAL_REQUIREMENT_STAGE,
    HISTORICAL_TEST_STAGE,
)
from testing_agent.domain.historical_test_case_artifacts import (
    VERIFICATION_RUN_RESULT,
    full_case_batch,
    verification_run_header,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.auth_runtime import AuthRuntime
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import AiGenerationStageContent


@pytest.fixture(params=("sqlite", "mysql"))
def history_api(api, request, monkeypatch):  # noqa: F811
    if request.param == "sqlite":
        yield api
        return
    database = request.getfixturevalue("mysql")
    with database.begin() as connection:
        if connection.scalar(select(AuthRuntime.id).where(AuthRuntime.id == 1)) is None:
            connection.execute(
                AuthRuntime.__table__.insert().values(
                    id=1, mode="local", fingerprint="", generation=0, reconcile_owner=""
                )
            )
    # TestClient and the fixture helpers invoke the async session from different loops.
    engine, sessions = async_sessions(database, poolclass=NullPool)

    async def session():
        async with sessions() as value:
            yield value

    monkeypatch.setattr(api.app.state, "test_sessions", sessions)
    monkeypatch.setitem(api.app.dependency_overrides, get_session, session)
    try:
        yield api
    finally:
        asyncio.run(engine.dispose())


def _old_requirement(client, headers, project_id):
    sprint = client.post(
        f"/v1/projects/{project_id}/sprints",
        headers=headers,
        json={
            "name": "历史迭代",
            "startTime": "2025-09-01T00:00:00Z",
            "endTime": "2025-10-01T00:00:00Z",
        },
    ).json()["data"]["sprintId"]
    return client.post(
        f"/v1/sprints/{sprint}/requirements", headers=headers, json={"name": "历史需求"}
    ).json()["data"]["requirementId"]


async def _seed_verification_cases(client, previous, foreign):
    async with client.app.state.test_sessions() as session:
        for suite_id, requirement_id in (("old-suite", previous), ("foreign-suite", foreign)):
            session.add(
                FunctionTestSuite(suite_id=suite_id, requirement_id=requirement_id, name=suite_id)
            )
        await session.flush()
        for number in range(10):
            steps = [{"action": "检查页面", "expected": "显示列表"}] * 3
            steps.append(
                {"action": "点击保存", "expected": "展示结果"}
                if number != 8
                else {"action": "鼠标悬停", "expected": "按钮变色"}
            )
            session.add(
                FunctionTestCase(
                    case_id=f"historical-case-{number}",
                    suite_id="foreign-suite" if number == 9 else "old-suite",
                    title=f"通用检查 {number}",
                    order_no=number,
                    invalidated_at=datetime.now(UTC) if number == 7 else None,
                    content={"preconditions": [], "steps": steps},
                )
            )
        await session.commit()


def _verification_pass(batch, *, needs_full=False, invalidate=False):
    findings = []
    for case in batch["candidateCases"]:
        request_full = needs_full and case["caseId"] == "historical-case-0"
        findings.append(
            {
                "caseId": case["caseId"],
                "caseSnapshotId": case["caseSnapshotId"],
                "decision": "needs_confirmation"
                if request_full
                else "invalidate"
                if invalidate
                else "reuse",
                "evidence": [{"kind": "step", "position": 4}],
                "reason": "合成结果，用于核验批次证据和回传约束",
                "modificationHint": None,
                "needsFullCase": request_full,
            }
        )
    return {
        **verification_run_header("historical_test_case_verification", batch),
        "impactId": batch["impact"]["impactId"],
        "batchId": batch["batchId"],
        "caseFindings": findings,
        "supplementalScenarios": [],
    }


def test_history_candidate_uses_same_project_adopted_material_and_independent_attempt(
    history_api,
    monkeypatch,
):
    client = history_api
    monkeypatch.setitem(client.app.dependency_overrides, verify_worker_token, lambda: None)
    _, headers = account(client, "historical-requirement")
    pid = project(client, headers)
    rid = requirement(client, headers, pid)
    previous = _old_requirement(client, headers, pid)
    foreign = requirement(client, headers, project(client, headers, "other-project"))
    asyncio.run(_seed_verification_cases(client, previous, foreign))
    old = material_artifact()
    old["functions"][0]["sections"][0]["items"][0]["text"] = "保存后展示历史结果"
    old["materialBlocks"][0]["content"]["text"] = "HISTORICAL-RAW-BLOCK-MARKER"
    previous_candidate = adopt_material(client, previous, headers=headers, content=json.dumps(old))
    adopt_material(client, foreign, headers=headers, content=json.dumps(old))
    current_candidate = adopt_material(client, rid, headers=headers)
    connection = seed_llm_connection(
        client,
        headers,
        project_id=pid,
        name="history",
        base_url="https://llm.example",
        api_key="test",
    )

    async def remove_new_slot_from_existing_chain():
        async with client.app.state.test_sessions() as session:
            stage_id = await session.scalar(
                select(AiGenerationStage.id)
                .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
                .where(
                    AiGenerateTask.requirement_id == rid,
                    AiGenerationStage.stage == HISTORICAL_REQUIREMENT_STAGE,
                )
            )
            await session.execute(
                delete(AiGenerationStageContent).where(
                    AiGenerationStageContent.stage_id == stage_id
                )
            )
            await session.execute(delete(AiGenerationStage).where(AiGenerationStage.id == stage_id))
            await session.commit()

    asyncio.run(remove_new_slot_from_existing_chain())
    chain = f"/v1/requirements/{rid}/generation/requirement_analysis"
    base = f"{chain}/stages/{HISTORICAL_REQUIREMENT_STAGE}"
    verification = f"{chain}/stages/{HISTORICAL_TEST_STAGE}"
    initial = client.get(base + "/current", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["data"]["candidateId"] is None
    request = {"connectionId": connection, "requestId": str(uuid4())}
    assert (
        client.post(verification + "/candidate-run", headers=headers, json=request).status_code
        == 400
    )
    response = client.post(base + "/candidate-run", headers=headers, json=request)
    assert response.status_code == 200, response.text
    receipt = response.json()["data"]
    assert client.post(base + "/candidate-run", headers=headers, json=request).json()["data"][
        "replayed"
    ]

    worker_id = "historical-worker"
    claim_response = client.post("/internal/ai-worker/tasks/claim", json={"workerId": worker_id})
    assert claim_response.status_code == 200, claim_response.text
    claim = claim_response.json()
    assert claim["attemptId"] == receipt["attemptId"]
    assert claim["currentStage"] == HISTORICAL_REQUIREMENT_STAGE
    internal = f"/internal/ai-worker/tasks/{claim['taskId']}"
    snapshot_response = client.get(internal + "/snapshot")
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()
    run = snapshot["run"]
    assert not run.get("documentDownloadUrl")
    assert client.get(internal + "/requirement-document").status_code == 404
    assert "HISTORICAL-RAW-BLOCK-MARKER" not in run["sourceContent"]
    assert "firstStepOutput" not in json.loads(snapshot["configJson"])
    payload = json.loads(run["sourceContent"])
    assert [item["requirementId"] for item in payload["historicalRequirements"]] == [previous]
    assert snapshot["candidateInput"]["selectedSources"][0]["candidateId"] == current_candidate
    assert previous_candidate != current_candidate

    output = {
        "schemaVersion": "0.1",
        "artifactType": "historical_requirement_relation_analysis",
        "requirementId": foreign,
        "materialSnapshotId": payload["currentRequirement"]["materialSnapshotId"],
        "relations": [],
        "openQuestions": [],
    }
    event = {"workerId": worker_id, "attemptId": claim["attemptId"], "status": "success"}
    rejected = client.post(
        internal + "/completed", json={**event, "resultYaml": json.dumps(output)}
    )
    assert rejected.status_code == 400, rejected.text
    output["requirementId"] = rid
    history = payload["historicalRequirements"][0]
    output["relations"] = [
        {
            "relationId": "relation-1",
            "historicalRequirementId": previous,
            "historicalMaterialSnapshotId": history["materialSnapshotId"],
            "relationType": "supplements",
            "impacts": [
                {
                    "impactId": "impact-1",
                    "reviewStatus": "proposed",
                    "ruleEffect": "still_applies",
                    "scope": {"roles": [], "states": [], "conditions": ["保存成功"]},
                    "previousRule": "保存后展示结果",
                    "currentRule": "保存后展示结果",
                    "changeSummary": "沿用保存后展示结果的规则",
                    "currentItemIds": [payload["currentRequirement"]["items"][0]["itemId"]],
                    "historicalItemIds": [history["items"][0]["itemId"]],
                }
            ],
        }
    ]
    inherited = output["relations"][0]["impacts"][0]
    output["relations"][0]["impacts"].extend(
        [
            {
                **inherited,
                "impactId": "modified-expectation",
                "ruleEffect": "changed",
                "currentRule": "保存后展示结果和处理状态",
                "changeSummary": "保存后的结果页增加处理状态，原展示预期随之调整",
            },
            {
                **inherited,
                "impactId": "added-submit-channel",
                "ruleEffect": "supplemented",
                "currentRule": "保存后展示结果，新增在移动端查看结果",
                "changeSummary": "新增在移动端查看保存结果，原结果页照常展示",
            },
            {**inherited, "impactId": "pending", "reviewStatus": "needs_confirmation"},
        ]
    )
    output["openQuestions"] = [{"impactId": "pending", "question": "是否适用于归档后的单据？"}]
    completed = client.post(
        internal + "/completed", json={**event, "resultYaml": json.dumps(output)}
    )
    assert completed.status_code == 204, completed.text
    candidates = client.get(base + "/candidates", headers=headers).json()["data"]["items"]
    assert len(candidates) == 1
    candidate = candidates[0]
    # Studio reads the same frozen input the Worker received to resolve item text.
    detail = client.get(f"{base}/candidates/{candidate['candidateId']}", headers=headers)
    assert json.loads(detail.json()["data"]["materialContent"]) == payload
    assert "HISTORICAL-RAW-BLOCK-MARKER" not in detail.json()["data"]["materialContent"]
    slot = client.get(base + "/current", headers=headers).json()["data"]
    adopted = client.post(
        base + "/adoption",
        headers=headers,
        json={
            "action": "adopt",
            "candidateId": candidate["candidateId"],
            "expectedCandidateToken": candidate["candidateToken"],
            "expectedAttemptId": claim["attemptId"],
            "expectedCurrentToken": slot["currentToken"],
            "requestId": str(uuid4()),
            "continueAfter": True,
            "connectionId": connection,
        },
    )
    assert adopted.status_code == 200, adopted.text
    adoption = adopted.json()["data"]
    assert adoption["continuationAttemptId"], adoption["continuationError"]
    adopted_slot = client.get(base + "/current", headers=headers).json()["data"]
    assert json.loads(adopted_slot["materialContent"]) == payload

    claimed = client.post("/internal/ai-worker/tasks/claim", json={"workerId": worker_id})
    assert claimed.status_code == 200, claimed.text
    task = claimed.json()
    assert task["currentStage"] == HISTORICAL_TEST_STAGE
    assert task["attemptId"] == adoption["continuationAttemptId"]
    assert task["attemptId"] != receipt["attemptId"]
    worker_route = f"/internal/ai-worker/tasks/{task['taskId']}"
    worker_input = client.get(worker_route + "/snapshot").json()
    frozen = json.loads(worker_input["run"]["sourceContent"])
    assert frozen["impactResultId"] == candidate["snapshotId"]
    assert [len(batch["candidateCases"]) for batch in frozen["batches"]] == [6, 1, 0]
    assert [batch["impact"]["impactId"] for batch in frozen["batches"]] == [
        "modified-expectation",
        "modified-expectation",
        "added-submit-channel",
    ]
    assert set(frozen["fullCases"]) == {f"historical-case-{number}" for number in range(7)}
    first_batch = frozen["batches"][0]
    assert [step["position"] for step in first_batch["candidateCases"][0]["steps"]] == [4]

    function_run = client.post(
        f"/v1/requirements/{rid}/generation/function/stages/requirement_analysis/candidate-run",
        headers=headers,
        json={"connectionId": connection},
    )
    assert function_run.status_code == 200, function_run.text
    assert function_run.json()["data"]["attemptId"] != task["attemptId"]
    first = _verification_pass(first_batch, needs_full=True)
    supplement = _verification_pass(frozen["batches"][2])
    del supplement["supplementalScenarios"]
    supplement["schemaVersion"] = "0.2"
    supplement["supplementalPoints"] = [
        {
            "pointId": "mobile-result",
            "title": "验证单据保存后在移动端可以查看保存结果",
        }
    ]
    result = {
        **verification_run_header(VERIFICATION_RUN_RESULT, frozen),
        "batches": [
            {"firstPass": first, "fullCasePass": None},
            {"firstPass": _verification_pass(frozen["batches"][1]), "fullCasePass": None},
            {"firstPass": supplement, "fullCasePass": None},
        ],
    }
    event = {"workerId": worker_id, "attemptId": task["attemptId"], "status": "success"}
    incomplete = client.post(
        worker_route + "/completed", json={**event, "resultYaml": json.dumps(result)}
    )
    assert incomplete.status_code == 400, incomplete.text
    follow_up = full_case_batch(frozen, first_batch, first)
    assert [case["caseId"] for case in follow_up["candidateCases"]] == ["historical-case-0"]
    result["batches"][0]["fullCasePass"] = _verification_pass(follow_up, invalidate=True)
    supplement["supplementalPoints"][0]["action"] = "打开移动端单据"
    excessive = client.post(
        worker_route + "/completed", json={**event, "resultYaml": json.dumps(result)}
    )
    assert excessive.status_code == 400, excessive.text
    del supplement["supplementalPoints"][0]["action"]
    verified = client.post(
        worker_route + "/completed", json={**event, "resultYaml": json.dumps(result)}
    )
    assert verified.status_code == 204, verified.text
    listed = client.get(verification + "/candidates", headers=headers).json()["data"]["items"]
    assert len(listed) == 1
    detail = client.get(f"{verification}/candidates/{listed[0]['candidateId']}", headers=headers)
    assert json.loads(detail.json()["data"]["content"]) == result
    # Studio reads the same frozen run input the Worker received (rule text, full cases).
    assert json.loads(detail.json()["data"]["materialContent"]) == frozen

    async def check_formal_case():
        async with client.app.state.test_sessions() as session:
            case = await session.scalar(
                select(FunctionTestCase).where(FunctionTestCase.case_id == "historical-case-0")
            )
            assert case.invalidated_at is None

    asyncio.run(check_formal_case())

    rerun = client.post(base + "/candidate-run", headers=headers, json={"connectionId": connection})
    assert rerun.status_code == 200, rerun.text

    async def load_rerun_input():
        async with client.app.state.test_sessions() as session:
            attempt = await session.get(AiGenerationAttempt, rerun.json()["data"]["attemptId"])
            return json.loads(attempt.input_snapshot_json["source"]["sourceContent"])

    known = asyncio.run(load_rerun_input())["knownRelations"]
    assert {edge["toRequirementId"] for edge in known} == {previous}
    assert {edge["relationType"] for edge in known} == {"depends_on", "changes", "supplements"}
