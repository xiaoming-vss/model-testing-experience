"""Exercise the history stage through its user and Worker HTTP entry points."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.pool import NullPool
from support.mysql_initialization import async_sessions, clear_schema, mysql  # noqa: F401
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

WORKER = "historical-worker"
RAW_BLOCK_MARKER = "HISTORICAL-RAW-BLOCK-MARKER"


@pytest.fixture(params=("sqlite", "mysql"))
def history_api(request, monkeypatch):
    if request.param == "sqlite":
        yield request.getfixturevalue("api")
        return
    # Skips here without a disposable MySQL, before an application is built for the test.
    database = request.getfixturevalue("mysql")
    clear_schema(database)
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

    client = request.getfixturevalue("api")
    monkeypatch.setattr(client.app.state, "test_sessions", sessions)
    monkeypatch.setitem(client.app.dependency_overrides, get_session, session)
    try:
        yield client
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


async def _remove_history_stage(client, rid):
    """Drop the history stage of the chain, as if the chain predated the stage."""
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
            delete(AiGenerationStageContent).where(AiGenerationStageContent.stage_id == stage_id)
        )
        await session.execute(delete(AiGenerationStage).where(AiGenerationStage.id == stage_id))
        await session.commit()


async def _stored_function_case(client, case_id):
    async with client.app.state.test_sessions() as session:
        return await session.scalar(
            select(FunctionTestCase).where(FunctionTestCase.case_id == case_id)
        )


async def _attempt_source(client, attempt_id):
    """Frozen ``sourceContent`` of an attempt, decoded."""
    async with client.app.state.test_sessions() as session:
        attempt = await session.get(AiGenerationAttempt, attempt_id)
        return json.loads(attempt.input_snapshot_json["source"]["sourceContent"])


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


def _relation_output(requirement_id, payload):
    """Relation analysis of ``requirement_id`` before any relation or question is added."""
    return {
        "schemaVersion": "0.1",
        "artifactType": "historical_requirement_relation_analysis",
        "requirementId": requirement_id,
        "materialSnapshotId": payload["currentRequirement"]["materialSnapshotId"],
        "relations": [],
        "openQuestions": [],
    }


def _add_one_relation(output, payload, previous):
    """Relate ``previous`` to the current requirement and list its impacts and question."""
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


def _verification_result(frozen):
    """Verification result for ``frozen`` with three first passes and no full-case pass yet."""
    supplement = _verification_pass(frozen["batches"][2])
    del supplement["supplementalScenarios"]
    supplement["schemaVersion"] = "0.2"
    supplement["supplementalPoints"] = [
        {"pointId": "mobile-result", "title": "验证单据保存后在移动端可以查看保存结果"}
    ]
    return {
        **verification_run_header(VERIFICATION_RUN_RESULT, frozen),
        "batches": [
            {
                "firstPass": _verification_pass(frozen["batches"][0], needs_full=True),
                "fullCasePass": None,
            },
            {"firstPass": _verification_pass(frozen["batches"][1]), "fullCasePass": None},
            {"firstPass": supplement, "fullCasePass": None},
        ],
    }


def _with_full_case_pass(result, frozen):
    """Record the full-case pass for the case the first pass asked to read in full."""
    follow_up = full_case_batch(frozen, frozen["batches"][0], result["batches"][0]["firstPass"])
    assert [case["caseId"] for case in follow_up["candidateCases"]] == ["historical-case-0"]
    result["batches"][0]["fullCasePass"] = _verification_pass(follow_up, invalidate=True)
    return result


@pytest.fixture
def history(history_api, monkeypatch):
    """Current requirement next to an older and a foreign one, each with adopted material."""
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
    old["materialBlocks"][0]["content"]["text"] = RAW_BLOCK_MARKER
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
    asyncio.run(_remove_history_stage(client, rid))
    chain = f"/v1/requirements/{rid}/generation/requirement_analysis"
    return SimpleNamespace(
        client=client,
        headers=headers,
        rid=rid,
        previous=previous,
        foreign=foreign,
        previous_candidate=previous_candidate,
        current_candidate=current_candidate,
        connection=connection,
        base=f"{chain}/stages/{HISTORICAL_REQUIREMENT_STAGE}",
        verification=f"{chain}/stages/{HISTORICAL_TEST_STAGE}",
        function_stage=f"/v1/requirements/{rid}/generation/function/stages/requirement_analysis",
    )


def _current(history):
    response = history.client.get(history.base + "/current", headers=history.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _start_history_run(history):
    """Run the history stage as the user; returns the request and its receipt."""
    request = {"connectionId": history.connection, "requestId": str(uuid4())}
    response = history.client.post(
        history.base + "/candidate-run", headers=history.headers, json=request
    )
    assert response.status_code == 200, response.text
    return request, response.json()["data"]


def _claim(history):
    """Let the history worker claim the pending attempt."""
    response = history.client.post("/internal/ai-worker/tasks/claim", json={"workerId": WORKER})
    assert response.status_code == 200, response.text
    return response.json()


def _snapshot(history, task_id):
    response = history.client.get(f"/internal/ai-worker/tasks/{task_id}/snapshot")
    assert response.status_code == 200, response.text
    return response.json()


def _complete(history, task_id, attempt_id, payload):
    """Report ``payload`` as the successful result of the attempt; returns the response."""
    return history.client.post(
        f"/internal/ai-worker/tasks/{task_id}/completed",
        json={
            "workerId": WORKER,
            "attemptId": attempt_id,
            "status": "success",
            "resultYaml": json.dumps(payload),
        },
    )


def _complete_history(history):
    """Start the history stage and relate the previous requirement to the current one."""
    _, receipt = _start_history_run(history)
    claim = _claim(history)
    payload = json.loads(_snapshot(history, claim["taskId"])["run"]["sourceContent"])
    output = _relation_output(history.rid, payload)
    _add_one_relation(output, payload, history.previous)
    completed = _complete(history, claim["taskId"], claim["attemptId"], output)
    assert completed.status_code == 204, completed.text
    candidates = history.client.get(history.base + "/candidates", headers=history.headers).json()[
        "data"
    ]["items"]
    return SimpleNamespace(receipt=receipt, claim=claim, payload=payload, candidates=candidates)


def _adopt_history(history, done):
    """Adopt the relation candidate and ask to continue; returns the adoption result."""
    candidate = done.candidates[0]
    response = history.client.post(
        history.base + "/adoption",
        headers=history.headers,
        json={
            "action": "adopt",
            "candidateId": candidate["candidateId"],
            "expectedCandidateToken": candidate["candidateToken"],
            "expectedAttemptId": done.claim["attemptId"],
            "expectedCurrentToken": _current(history)["currentToken"],
            "requestId": str(uuid4()),
            "continueAfter": True,
            "connectionId": history.connection,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _verification_ready(history):
    """Adopt the relations and claim the verification attempt they continue into."""
    done = _complete_history(history)
    _adopt_history(history, done)
    task = _claim(history)
    frozen = json.loads(_snapshot(history, task["taskId"])["run"]["sourceContent"])
    return SimpleNamespace(relations=done, task=task, frozen=frozen)


def test_history_stage_dispatches_one_replayable_attempt(history):
    slot = _current(history)
    refused = history.client.post(
        history.verification + "/candidate-run",
        headers=history.headers,
        json={"connectionId": history.connection, "requestId": str(uuid4())},
    )
    request, receipt = _start_history_run(history)
    replay = history.client.post(
        history.base + "/candidate-run", headers=history.headers, json=request
    )
    claim = _claim(history)

    assert slot["candidateId"] is None
    assert refused.status_code == 400
    assert replay.json()["data"]["replayed"]
    assert claim["attemptId"] == receipt["attemptId"]
    assert claim["currentStage"] == HISTORICAL_REQUIREMENT_STAGE


def test_history_worker_input_and_result_stay_within_the_current_requirement(history):
    _start_history_run(history)
    claim = _claim(history)
    document = history.client.get(
        f"/internal/ai-worker/tasks/{claim['taskId']}/requirement-document"
    )
    snapshot = _snapshot(history, claim["taskId"])
    run = snapshot["run"]
    payload = json.loads(run["sourceContent"])
    rejected = _complete(
        history, claim["taskId"], claim["attemptId"], _relation_output(history.foreign, payload)
    )

    assert not run.get("documentDownloadUrl")
    assert document.status_code == 404
    assert RAW_BLOCK_MARKER not in run["sourceContent"]
    assert "firstStepOutput" not in json.loads(snapshot["configJson"])
    assert [item["requirementId"] for item in payload["historicalRequirements"]] == [
        history.previous
    ]
    assert (
        snapshot["candidateInput"]["selectedSources"][0]["candidateId"] == history.current_candidate
    )
    assert history.previous_candidate != history.current_candidate
    assert rejected.status_code == 400, rejected.text


def test_adopted_relations_become_known_and_continue_to_verification(history):
    done = _complete_history(history)
    candidate = done.candidates[0]
    detail = history.client.get(
        f"{history.base}/candidates/{candidate['candidateId']}", headers=history.headers
    ).json()["data"]
    adoption = _adopt_history(history, done)
    slot = _current(history)
    task = _claim(history)
    rerun = history.client.post(
        history.base + "/candidate-run",
        headers=history.headers,
        json={"connectionId": history.connection},
    )
    assert rerun.status_code == 200, rerun.text
    known = asyncio.run(_attempt_source(history.client, rerun.json()["data"]["attemptId"]))[
        "knownRelations"
    ]

    assert len(done.candidates) == 1
    assert json.loads(detail["materialContent"]) == done.payload
    assert RAW_BLOCK_MARKER not in detail["materialContent"]
    assert adoption["continuationAttemptId"], adoption["continuationError"]
    assert json.loads(slot["materialContent"]) == done.payload
    assert task["currentStage"] == HISTORICAL_TEST_STAGE
    assert task["attemptId"] == adoption["continuationAttemptId"]
    assert task["attemptId"] != done.receipt["attemptId"]
    assert {edge["toRequirementId"] for edge in known} == {history.previous}
    assert {edge["relationType"] for edge in known} == {"depends_on", "changes", "supplements"}


def test_verification_input_freezes_impacts_and_leaves_other_runs_independent(history):
    ready = _verification_ready(history)
    candidate = ready.relations.candidates[0]
    frozen = ready.frozen
    function_run = history.client.post(
        history.function_stage + "/candidate-run",
        headers=history.headers,
        json={"connectionId": history.connection},
    )

    assert frozen["impactResultId"] == candidate["snapshotId"]
    assert [len(batch["candidateCases"]) for batch in frozen["batches"]] == [6, 1, 0]
    assert [batch["impact"]["impactId"] for batch in frozen["batches"]] == [
        "modified-expectation",
        "modified-expectation",
        "added-submit-channel",
    ]
    assert set(frozen["fullCases"]) == {f"historical-case-{number}" for number in range(7)}
    assert [step["position"] for step in frozen["batches"][0]["candidateCases"][0]["steps"]] == [4]
    assert function_run.status_code == 200, function_run.text
    assert function_run.json()["data"]["attemptId"] != ready.task["attemptId"]


def test_verification_completion_needs_the_full_case_pass_and_known_point_fields(history):
    ready = _verification_ready(history)
    result = _with_full_case_pass(_verification_result(ready.frozen), ready.frozen)
    result["batches"][2]["firstPass"]["supplementalPoints"][0]["action"] = "打开移动端单据"

    incomplete = _complete(
        history, ready.task["taskId"], ready.task["attemptId"], _verification_result(ready.frozen)
    )
    excessive = _complete(history, ready.task["taskId"], ready.task["attemptId"], result)

    assert incomplete.status_code == 400, incomplete.text
    assert excessive.status_code == 400, excessive.text


def test_verified_result_is_stored_without_touching_formal_cases(history):
    ready = _verification_ready(history)
    result = _with_full_case_pass(_verification_result(ready.frozen), ready.frozen)
    verified = _complete(history, ready.task["taskId"], ready.task["attemptId"], result)
    assert verified.status_code == 204, verified.text
    listed = history.client.get(
        history.verification + "/candidates", headers=history.headers
    ).json()["data"]["items"]
    detail = history.client.get(
        f"{history.verification}/candidates/{listed[0]['candidateId']}",
        headers=history.headers,
    ).json()["data"]
    case = asyncio.run(_stored_function_case(history.client, "historical-case-0"))

    assert len(listed) == 1
    assert json.loads(detail["content"]) == result
    assert json.loads(detail["materialContent"]) == ready.frozen
    assert case.invalidated_at is None
