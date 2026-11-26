"""HTTP workflow from trial candidates to adoption and formal import."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
import yaml as yaml_module
from support.order_api import make_order
from support.project_api import account, api, project, requirement  # noqa: F401
from support.requirement_versions import material_artifact, points_artifact, scope_artifact
from support.ui_generation_fixtures import FIXTURES as UI_FIXTURES
from support.ui_generation_fixtures import read as ui_fixture

from testing_agent.api.deps_common import get_file_service
from testing_agent.domain.historical_test_case_artifacts import (
    VERIFICATION_RUN_RESULT,
    verification_run_header,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.generation_dispatch_application import CandidateDispatchApplication
from testing_agent.services.repo_gitlab_access import RepoGitlabAccess
from testing_agent.services.repository_profile import RepositoryProfileService
from testing_agent.services.requirement_material_source import (
    material_reference_fields,
    material_source,
)
from testing_agent.services.service_instance import instance_key
from testing_agent.services.stage_storage.authorization import DirectWorkerAuthority
from testing_agent.services.stage_storage.payload import worker_payloads
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.ui_generation_contracts import validate_ui_output
from testing_agent.services.ui_generation_source import UiGenerationSourceService


class Storage:
    def __init__(self, content):
        self.content = content

    def get_object(self, key):
        assert key == "document"
        return {"Body": self}

    def iter_chunks(self, chunk_size):
        yield self.content

    def close(self):
        pass


@pytest.mark.parametrize("with_history", (False, True))
def test_http_candidate_trial_adoption_and_import(api, monkeypatch, with_history):  # noqa: F811
    user, headers = account(api, "workflow-complete")
    pid = project(api, headers)
    rid = requirement(api, headers, pid)
    doc = b"verified document"
    digest = sha256(doc).hexdigest()
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=Storage(doc))
    api.app.dependency_overrides[get_file_service] = lambda: files

    async def seed():
        async with api.app.state.test_sessions() as session:
            req = await session.scalar(
                sa.select(Requirement).where(Requirement.requirement_id == rid)
            )
            req.document_type, req.document_file_id = "docx", "document"
            req.document_filename, req.document_hash = "requirement.docx", digest
            session.add(
                StoredFile(
                    file_id="document",
                    project_id=pid,
                    uploaded_by=user["userId"],
                    filename="requirement.docx",
                    content_type="application/octet-stream",
                    size=len(doc),
                    sha256=digest,
                    bucket="bucket",
                    object_key="document",
                    staging_key="",
                    status="attached",
                    purpose="requirement",
                    resource_type="requirement",
                    resource_id=rid,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            session.add(
                IntegrationConnection(
                    connection_id="llm",
                    user_id=user["userId"],
                    project_id=pid,
                    provider="llm",
                    name="model",
                    status="active",
                    secret_json={"apiKey": "test-only"},
                )
            )
            await session.commit()

    asyncio.run(seed())
    bases = {
        kind: f"/v1/requirements/{rid}/generation/{kind}"
        for kind in ("requirement_analysis", "function")
    }
    for kind in bases:
        config = api.post(
            f"/v1/requirements/{rid}/design/{kind}/configuration", headers=headers, json={}
        )
        assert config.status_code == 200, config.text
        initialized = api.post(
            bases[kind] + "/candidate-chain",
            headers=headers,
            json={"taskId": config.json()["data"]["taskId"]},
        )
        assert initialized.status_code == 200, initialized.text

    def launch(kind, stage, selections=None):
        body = {
            "connectionId": "llm",
            "requestId": str(uuid4()),
            "generationMode": "trial" if selections is not None else "current",
        }
        if selections is not None:
            body["sourceSelections"] = selections
        response = api.post(
            f"{bases[kind]}/stages/{stage}/candidate-run", headers=headers, json=body
        )
        assert response.status_code == 200, response.text
        return body, response.json()["data"]

    def complete(kind, stage_name, request, result, output, fmt="json"):
        if with_history and stage_name == "detailed_cases":
            output = {**yaml_module.safe_load(output), "historicalCaseFindings": []}
            fmt = "json"

        async def emit():
            async with api.app.state.test_sessions() as session:
                stage = await session.scalar(
                    sa.select(AiGenerationStage)
                    .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
                    .where(
                        AiGenerateTask.requirement_id == rid,
                        AiGenerateTask.task_type
                        == (
                            "requirement_analysis"
                            if kind == "requirement_analysis"
                            else "functional_case_generate"
                        ),
                        AiGenerationStage.stage == stage_name,
                    )
                )
                await StageWorkerTransitions(session).completed(
                    stage.id,
                    result["attemptId"],
                    request["requestId"],
                    content=json.dumps(output, ensure_ascii=False) if fmt == "json" else output,
                    output_format=fmt,
                    output_context=None,
                )
                await session.commit()

        asyncio.run(emit())
        response = api.get(f"{bases[kind]}/stages/{stage_name}/candidates", headers=headers)
        assert response.status_code == 200, response.text
        return next(
            item
            for item in response.json()["data"]["items"]
            if item["currentAttemptId"] == result["attemptId"]
        )

    def source(candidate, kind, stage):
        return {
            "chainKind": kind,
            "stage": stage,
            "sourceKind": "candidate",
            "candidateId": candidate["candidateId"],
            "snapshotId": candidate["snapshotId"],
            "expectedCandidateToken": candidate["candidateToken"],
        }

    def adopt(candidate, kind, stage):
        url = f"{bases[kind]}/stages/{stage}"
        current = api.get(url + "/current", headers=headers).json()["data"]
        body = {
            "action": "adopt",
            "candidateId": candidate["candidateId"],
            "expectedCandidateToken": candidate["candidateToken"],
            "expectedAttemptId": candidate["currentAttemptId"],
            "expectedCurrentToken": current["currentToken"],
            "requestId": str(uuid4()),
        }
        preflight = api.post(url + "/adoption/check", headers=headers, json=body)
        assert preflight.status_code == 200 and preflight.json()["data"]["canAdopt"], preflight.text
        adopted = api.post(url + "/adoption", headers=headers, json=body)
        assert adopted.status_code == 200, adopted.text
        return adopted.json()["data"]["contentToken"]

    req, run = launch("requirement_analysis", "extracting_text")
    material = complete("requirement_analysis", "extracting_text", req, run, material_artifact())

    async def read_snapshot(result):
        async with api.app.state.test_sessions() as session:
            attempt = await session.get(AiGenerationAttempt, result["attemptId"])
            return attempt.input_snapshot_json

    if with_history:
        adopt(material, "requirement_analysis", "extracting_text")
        relation_req, relation_run = launch(
            "requirement_analysis", "historical_requirement_relations"
        )
        relation_snapshot = asyncio.run(read_snapshot(relation_run))
        history_source = json.loads(relation_snapshot["source"]["sourceContent"])
        relation = complete(
            "requirement_analysis",
            "historical_requirement_relations",
            relation_req,
            relation_run,
            {
                "schemaVersion": "0.1",
                "artifactType": "historical_requirement_relation_analysis",
                "requirementId": rid,
                "materialSnapshotId": history_source["currentRequirement"]["materialSnapshotId"],
                "relations": [],
                "openQuestions": [],
            },
        )
        adopt(relation, "requirement_analysis", "historical_requirement_relations")
        history_req, history_run = launch(
            "requirement_analysis", "historical_test_case_verification"
        )
        history_snapshot = asyncio.run(read_snapshot(history_run))
        history_input = json.loads(history_snapshot["source"]["sourceContent"])
        history_result = {
            **verification_run_header(VERIFICATION_RUN_RESULT, history_input),
            "batches": [],
        }
        verification = complete(
            "requirement_analysis",
            "historical_test_case_verification",
            history_req,
            history_run,
            history_result,
        )
        adopt(verification, "requirement_analysis", "historical_test_case_verification")

    req, run = launch(
        "function",
        "requirement_analysis",
        [source(material, "requirement_analysis", "extracting_text")],
    )
    analysis = complete("function", "requirement_analysis", req, run, scope_artifact())
    req, run = launch(
        "function", "case_names", [source(analysis, "function", "requirement_analysis")]
    )
    points = complete("function", "case_names", req, run, points_artifact())
    points_detail = api.get(
        bases["function"] + f"/stages/case_names/candidates/{points['candidateId']}",
        headers=headers,
    )
    assert points_detail.status_code == 200, points_detail.text
    assert json.loads(points_detail.json()["data"]["materialContent"]) == material_artifact()
    revision_body = {
        "expectedCandidateToken": points["candidateToken"],
        "expectedAttemptId": points["currentAttemptId"],
        "connectionId": "llm",
        "instruction": "补充边界条件",
        "requestId": str(uuid4()),
    }
    revision_url = (
        bases["function"] + f"/stages/case_names/candidates/{points['candidateId']}/revision"
    )
    stale_revision = api.post(
        revision_url,
        headers=headers,
        json={**revision_body, "expectedCandidateToken": "outdated", "requestId": str(uuid4())},
    )
    assert (
        stale_revision.status_code == 400
        and stale_revision.json()["data"]["reason"] == "concurrent_change"
    ), stale_revision.text
    revision = api.post(revision_url, headers=headers, json=revision_body)
    assert revision.status_code == 200, revision.text
    revision_replay = api.post(revision_url, headers=headers, json=revision_body)
    assert revision_replay.status_code == 200 and revision_replay.json()["data"]["replayed"]
    revised_points = complete(
        "function", "case_names", revision_body, revision.json()["data"], points_artifact()
    )
    assert revised_points["derivedFromCandidateId"] == points["candidateId"]
    second_revision_body = {
        **revision_body,
        "expectedCandidateToken": revised_points["candidateToken"],
        "expectedAttemptId": revised_points["currentAttemptId"],
        "instruction": "再补充异常场景",
        "requestId": str(uuid4()),
    }
    second_revision = api.post(
        bases["function"]
        + f"/stages/case_names/candidates/{revised_points['candidateId']}/revision",
        headers=headers,
        json=second_revision_body,
    )
    assert second_revision.status_code == 200, second_revision.text
    revised_again = complete(
        "function",
        "case_names",
        second_revision_body,
        second_revision.json()["data"],
        points_artifact(),
    )
    assert revised_again["derivedFromCandidateId"] == revised_points["candidateId"]
    detail_response = api.get(
        bases["function"] + f"/stages/case_names/candidates/{revised_again['candidateId']}",
        headers=headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    manual = api.post(
        bases["function"] + f"/stages/case_names/candidates/{revised_again['candidateId']}/derive",
        headers=headers,
        json={
            "expectedCandidateToken": revised_again["candidateToken"],
            "expectedAttemptId": revised_again["currentAttemptId"],
            "content": detail_response.json()["data"]["content"],
            "requestId": str(uuid4()),
        },
    )
    assert manual.status_code == 200, manual.text
    manual_candidate = manual.json()["data"]
    revised_case_req, revised_case_run = launch(
        "function",
        "detailed_cases",
        [
            source(analysis, "function", "requirement_analysis"),
            source(manual_candidate, "function", "case_names"),
        ],
    )
    revised_cases = complete(
        "function",
        "detailed_cases",
        revised_case_req,
        revised_case_run,
        "cases:\n  - case_id: revised-case\n    title: revised\n",
        "yaml",
    )
    assert revised_cases["generationMode"] == "trial"
    req, run = launch(
        "function",
        "detailed_cases",
        [
            source(analysis, "function", "requirement_analysis"),
            source(points, "function", "case_names"),
        ],
    )
    cases = complete(
        "function",
        "detailed_cases",
        req,
        run,
        "cases:\n  - case_id: graph-case\n    title: example\n",
        "yaml",
    )
    if with_history:
        case_snapshot = asyncio.run(read_snapshot(run))
        planning = case_snapshot["config"]["historyCasePlanning"]
        assert planning["verification"] == history_result
        assert json.loads(planning["input"]) == history_input
    else:
        adopt(material, "requirement_analysis", "extracting_text")
    options_before_profile = api.get(
        f"/v1/requirements/{rid}/generation/ui/source-options", headers=headers
    )
    assert options_before_profile.status_code == 200, options_before_profile.text
    assert options_before_profile.json()["data"]["currentProfile"] is None
    adopt(analysis, "function", "requirement_analysis")
    adopt(points, "function", "case_names")
    current_points = api.get(bases["function"] + "/stages/case_names/current", headers=headers)
    assert current_points.status_code == 200, current_points.text
    assert json.loads(current_points.json()["data"]["materialContent"]) == material_artifact()
    token = adopt(cases, "function", "detailed_cases")

    async def replace_document(content):
        async with api.app.state.test_sessions() as session:
            requirement_row = await session.scalar(
                sa.select(Requirement).where(Requirement.requirement_id == rid)
            )
            file_row = await session.scalar(
                sa.select(StoredFile).where(StoredFile.file_id == "document")
            )
            requirement_row.document_hash = sha256(content).hexdigest()
            file_row.sha256, file_row.size = sha256(content).hexdigest(), len(content)
            await session.commit()
        files.storage.content = content

    asyncio.run(replace_document(b"changed requirement"))
    stale_source_revision = api.post(
        revision_url,
        headers=headers,
        json={**revision_body, "requestId": str(uuid4())},
    )
    assert (
        stale_source_revision.status_code == 400
        and stale_source_revision.json()["data"]["reason"] == "source_stale"
    ), stale_source_revision.text
    asyncio.run(replace_document(doc))
    graph_url = bases["function"] + "/relations/current"
    empty_graph = api.get(graph_url, headers=headers, params={"currentToken": token})
    assert empty_graph.status_code == 200 and empty_graph.json()["data"]["status"] == "not_started"
    graph_body = {"currentToken": token, "connectionId": "llm", "requestId": str(uuid4())}
    graph_run = api.post(graph_url + "/run", headers=headers, json=graph_body)
    assert graph_run.status_code == 200 and not graph_run.json()["data"]["replayed"], graph_run.text
    graph_replay = api.post(graph_url + "/run", headers=headers, json=graph_body)
    assert graph_replay.status_code == 200 and graph_replay.json()["data"]["replayed"]

    async def complete_graph():
        async with api.app.state.test_sessions() as session:
            attempt = await session.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.id == graph_run.json()["data"]["attemptId"]
                )
            )
            await StageWorkerTransitions(session).completed(
                attempt.stage_id,
                attempt.id,
                graph_body["requestId"],
                content=json.dumps({"schema_version": "2.0", "main_paths": [], "edges": []}),
                output_format="json",
                output_context=None,
            )
            await session.commit()

    asyncio.run(complete_graph())
    graph_current = api.get(graph_url, headers=headers, params={"currentToken": token})
    assert (
        graph_current.status_code == 200 and graph_current.json()["data"]["status"] == "success"
    ), graph_current.text
    current_leaf = api.get(bases["function"] + "/stages/detailed_cases/current", headers=headers)
    assert current_leaf.json()["data"]["sourceAttemptId"] == cases["currentAttemptId"]
    expected_basis = {
        ("requirement_analysis", "extracting_text", material["candidateId"], False),
        ("function", "requirement_analysis", analysis["candidateId"], True),
        ("function", "case_names", points["candidateId"], True),
    }
    if with_history:
        expected_basis.update(
            {
                (
                    "requirement_analysis",
                    "historical_requirement_relations",
                    relation["candidateId"],
                    False,
                ),
                (
                    "requirement_analysis",
                    "historical_test_case_verification",
                    verification["candidateId"],
                    True,
                ),
            }
        )
    assert {
        (item["chainKind"], item["stage"], item["candidateId"], item["direct"])
        for item in current_leaf.json()["data"]["basisSources"]
    } == expected_basis
    url = bases["function"] + "/stages/detailed_cases/current"
    preview = api.post(
        url + "/import-preview", headers=headers, json={"expectedCurrentToken": token}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    body = {
        "expectedCurrentToken": token,
        "expectedLineageHash": data["fullLineageHash"],
        "previewToken": data["previewToken"],
        "requestId": str(uuid4()),
    }
    imported = api.post(url + "/import", headers=headers, json=body)
    assert imported.status_code == 200 and imported.json()["data"]["imported"], imported.text
    history = api.get(
        f"/v1/requirements/{rid}/design/function/runs",
        headers=headers,
        params={"pipelineFilter": "imported"},
    )
    assert history.status_code == 200, history.text
    imported_run = next(
        item
        for item in history.json()["data"]["items"]
        if item["runId"] == cases["currentAttemptId"]
    )
    assert imported_run["reviewStatus"] == "approved" and imported_run["importStatus"] == "imported"
    assert imported_run["importedTargets"]
    detail = api.get(
        f"/v1/function-case-generate-task-runs/{cases['currentAttemptId']}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["reviewStatus"] == "approved"
    assert detail.json()["data"]["importStatus"] == "imported"
    replay = api.post(url + "/import", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["data"]["replayed"]
    chain = api.get(bases["function"], headers=headers)
    assert chain.status_code == 200, chain.text
    chain_data = chain.json()["data"]
    assert chain_data["candidateMode"] is True
    final_stage = next(item for item in chain_data["stages"] if item["stage"] == "detailed_cases")
    assert final_stage["state"] == "approved"
    assert not {"versions", "latestVersion", "draft"} & final_stage.keys()

    async def count():
        async with api.app.state.test_sessions() as session:
            return await session.scalar(
                sa.select(sa.func.count())
                .select_from(FunctionTestCase)
                .where(FunctionTestCase.title == "example")
            )

    assert asyncio.run(count()) == 1

    async def profile_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
        current = kwargs["current_material"]
        return {
            "taskId": task.task_id,
            "taskType": task.task_type,
            "requirementId": task.requirement_id,
            "requirement": {"documentContent": material_source(current)},
            "bindings": [
                {
                    "bindingId": "frontend-binding",
                    "softwareRepositoryId": "frontend-binding",
                    "repositoryId": "frontend",
                    "instanceUrl": "https://gitlab.example.com",
                    "pathWithNamespace": "team/frontend",
                    "branch": "main",
                    "headCommit": "commit-a",
                    "cloneUrl": "https://private.example/repo",
                    "connectionId": "private-connection",
                }
            ],
            **material_reference_fields(current),
        }

    monkeypatch.setattr(RepositoryProfileService, "build_snapshot", profile_snapshot)
    profile_task = api.post(
        f"/v1/projects/{pid}/repository-profile-tasks", headers=headers, json={"requirementId": rid}
    )
    assert profile_task.status_code == 200, profile_task.text
    profile_task_id = profile_task.json()["data"]["taskId"]
    profile_run = api.post(
        f"/v1/repository-profile-tasks/{profile_task_id}/run",
        headers=headers,
        json={"connectionId": "llm"},
    )
    assert profile_run.status_code == 200, profile_run.text

    async def complete_profile():
        async with api.app.state.test_sessions() as session:
            attempt = await session.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.execution_id == profile_run.json()["data"]["runId"]
                )
            )
            await StageWorkerTransitions(session).completed(
                attempt.stage_id,
                attempt.id,
                attempt.worker_task_id,
                content=json.dumps(
                    {
                        "repositories": [
                            {
                                "repositoryId": "frontend",
                                "pathWithNamespace": "team/frontend",
                                "role": "frontend",
                                "responsibilitySummary": "ui",
                                "techStack": [],
                                "keyPaths": [],
                                "confidence": 0.9,
                                "evidence": [],
                            }
                        ],
                        "overallSummary": "profile",
                    }
                ),
                output_format="json",
                output_context=None,
            )
            await session.commit()

    asyncio.run(complete_profile())
    profile_base = f"/v1/requirements/{rid}/repository-profile"
    current_profile = api.get(profile_base + "/current", headers=headers)
    assert (
        current_profile.status_code == 200 and current_profile.json()["data"]["candidateId"] is None
    )
    profile_candidates = api.get(profile_base + "/candidates", headers=headers)
    assert profile_candidates.status_code == 200 and profile_candidates.json()["data"]["total"] == 1
    profile_candidate = profile_candidates.json()["data"]["items"][0]
    before_adoption_options = api.get(
        f"/v1/requirements/{rid}/generation/ui/source-options", headers=headers
    )
    assert before_adoption_options.status_code == 200, before_adoption_options.text
    assert before_adoption_options.json()["data"]["currentProfile"] is None
    detail = api.get(
        profile_base + "/candidates/" + profile_candidate["candidateId"], headers=headers
    )
    assert (
        detail.status_code == 200
        and json.loads(detail.json()["data"]["content"])["overallSummary"] == "profile"
    )
    profile_adopt = {
        "action": "adopt",
        "candidateId": profile_candidate["candidateId"],
        "expectedCandidateToken": profile_candidate["candidateToken"],
        "expectedAttemptId": profile_candidate["currentAttemptId"],
        "expectedCurrentToken": current_profile.json()["data"]["currentToken"],
        "requestId": str(uuid4()),
    }
    _, viewer = account(api, "profile-viewer")
    added_viewer = api.post(
        f"/v1/projects/{pid}/members",
        headers=headers,
        json={"name": "profile-viewer", "role": "viewer"},
    )
    assert added_viewer.status_code == 200, added_viewer.text
    assert (
        api.post(
            revision_url,
            headers=viewer,
            json={**revision_body, "requestId": str(uuid4())},
        ).status_code
        == 403
    )
    assert api.get(graph_url, headers=viewer, params={"currentToken": token}).status_code == 200
    assert (
        api.post(
            graph_url + "/run", headers=viewer, json={**graph_body, "requestId": str(uuid4())}
        ).status_code
        == 403
    )
    assert api.get(profile_base + "/candidates", headers=viewer).status_code == 200
    assert (
        api.post(profile_base + "/current/adopt", headers=viewer, json=profile_adopt).status_code
        == 403
    )
    adopted_profile = api.post(profile_base + "/current/adopt", headers=headers, json=profile_adopt)
    assert adopted_profile.status_code == 200, adopted_profile.text
    again = api.post(profile_base + "/current/adopt", headers=headers, json=profile_adopt)
    assert again.status_code == 200 and again.json()["data"]["replayed"]
    options = api.get(f"/v1/requirements/{rid}/generation/ui/source-options", headers=headers)
    assert options.status_code == 200, options.text
    assert (
        options.json()["data"]["currentProfile"]["candidateId"] == profile_candidate["candidateId"]
    )
    assert options.json()["data"]["currentProfile"]["repositories"][0]["commit"] == "commit-a"
    assert "private.example" not in options.text and "private-connection" not in options.text
    monkeypatch.setattr(
        UiGenerationSourceService,
        "resolve_binding_access",
        AsyncMock(
            return_value=RepoGitlabAccess("ui-connection", "https://gitlab.example.com", "test")
        ),
    )
    monkeypatch.setattr(
        UiGenerationSourceService,
        "_project",
        AsyncMock(
            return_value={
                "cloneUrl": "https://gitlab.example.com/team/frontend.git",
                "pathWithNamespace": "team/frontend",
            }
        ),
    )
    monkeypatch.setattr(
        UiGenerationSourceService, "resolve_latest_commit", AsyncMock(return_value="commit-b")
    )
    checked_source = api.post(
        f"/v1/requirements/{rid}/generation/ui/source-check",
        headers=headers,
        json={
            "profileCandidateId": profile_candidate["candidateId"],
            "repositoryId": "frontend",
            "pinnedCommit": "commit-a",
        },
    )
    assert checked_source.status_code == 200 and checked_source.json()["data"]["changed"]
    blocked_legacy_source = api.post(
        f"/v1/requirements/{rid}/generation/ui/source-check",
        headers=headers,
        json={
            "profileCandidateId": "old-profile",
            "repositoryId": "frontend",
            "pinnedCommit": "commit-a",
        },
    )
    assert blocked_legacy_source.status_code == 400

    async def seed_ui_source():
        async with api.app.state.test_sessions() as session:
            session.add(
                SoftwareRepository(
                    software_repository_id="frontend-binding",
                    project_id=pid,
                    name="frontend",
                    description="",
                    base_path="",
                    repository_project_id="frontend",
                    repository_group_id="group",
                    repository_instance_key=instance_key("https://gitlab.example.com"),
                    repository_path="team/frontend",
                    repository_name="frontend",
                    repository_instance_url="https://gitlab.example.com",
                    version=1,
                    created_by_user_id=user["userId"],
                )
            )
            session.add(
                FunctionTestSuite(suite_id="ui-source-suite", requirement_id=rid, name="功能")
            )
            session.add(
                UiTestSuite(
                    suite_id="ui-target-suite", project_id=pid, requirement_id=rid, name="UI"
                )
            )
            await session.flush()
            session.add(
                FunctionTestCase(
                    case_id="C1",
                    suite_id="ui-source-suite",
                    title="显示记录名称",
                    content=ui_fixture("cases")[0]["content"],
                )
            )
            await session.commit()

    asyncio.run(seed_ui_source())
    ui_base = f"/v1/requirements/{rid}/generation/ui"
    bases["ui"] = ui_base
    ui_config = api.post(
        f"/v1/requirements/{rid}/design/ui/configuration", headers=headers, json={}
    )
    assert ui_config.status_code == 200, ui_config.text
    initialized = api.post(
        ui_base + "/candidate-chain",
        headers=headers,
        json={"taskId": ui_config.json()["data"]["taskId"]},
    )
    assert initialized.status_code == 200, initialized.text

    def ui_launch(stage, **extra):
        body = {"connectionId": "llm", "requestId": str(uuid4()), **extra}
        result = api.post(f"{ui_base}/stages/{stage}/candidate-run", headers=headers, json=body)
        return body, result

    _, missing_repository = ui_launch("ui_surface", functionCaseIds=["C1"])
    assert missing_repository.status_code == 400

    _, stale_profile = ui_launch(
        "ui_surface",
        sourceRepositoryId="frontend",
        sourceProfileCandidateId="old-profile",
        functionCaseIds=["C1"],
    )
    assert stale_profile.status_code == 400
    assert stale_profile.json()["data"]["reason"] == "concurrent_change"
    unauthorized_ui = api.post(
        f"{ui_base}/stages/ui_surface/candidate-run",
        headers=viewer,
        json={"connectionId": "llm", "sourceRepositoryId": "frontend", "functionCaseIds": ["C1"]},
    )
    assert unauthorized_ui.status_code == 403

    async def set_profile_token(token):
        async with api.app.state.test_sessions() as session:
            await session.execute(
                sa.update(AiGenerationStageContent)
                .where(
                    AiGenerationStageContent.source_candidate_id == profile_candidate["candidateId"]
                )
                .values(content_token=token)
            )
            await session.commit()

    async def project_changes_profile(self, *args):
        await set_profile_token("changed-during-gitlab-read")
        return {
            "cloneUrl": "https://gitlab.example.com/team/frontend.git",
            "pathWithNamespace": "team/frontend",
        }

    monkeypatch.setattr(UiGenerationSourceService, "_project", project_changes_profile)
    _, raced = ui_launch("ui_surface", sourceRepositoryId="frontend", functionCaseIds=["C1"])
    assert raced.status_code == 400 and raced.json()["data"]["reason"] == "concurrent_change", (
        raced.text
    )
    asyncio.run(set_profile_token(adopted_profile.json()["data"]["contentToken"]))
    monkeypatch.setattr(
        UiGenerationSourceService,
        "_project",
        AsyncMock(
            return_value={
                "cloneUrl": "https://gitlab.example.com/team/frontend.git",
                "pathWithNamespace": "team/frontend",
            }
        ),
    )

    def ui_complete(stage, body, response, fixture, *, yaml=False):
        if yaml:
            content = yaml_module.safe_load((UI_FIXTURES / (fixture + ".yaml")).read_text())
            content[0]["stepsJson"][0].update(locatorType="css", locatorValue="#name")
            content[0]["stepsJson"][0].pop("missingFields", None)
            output = yaml_module.safe_dump(content, allow_unicode=True)
        else:
            output = json.dumps(ui_fixture(fixture), ensure_ascii=False)

        async def emit():
            async with api.app.state.test_sessions() as session:
                attempt = await session.scalar(
                    sa.select(AiGenerationAttempt).where(
                        AiGenerationAttempt.id == response.json()["data"]["attemptId"]
                    )
                )
                validate_ui_output(
                    SimpleNamespace(snapshot_json=attempt.input_snapshot_json["source"]),
                    stage,
                    output,
                )
                await StageWorkerTransitions(session).completed(
                    attempt.stage_id,
                    attempt.id,
                    body["requestId"],
                    content=output,
                    output_format="yaml" if yaml else "json",
                    output_context=None,
                )
                await session.commit()

        asyncio.run(emit())
        listing = api.get(f"{ui_base}/stages/{stage}/candidates", headers=headers)
        assert listing.status_code == 200, listing.text
        return next(
            item
            for item in listing.json()["data"]["items"]
            if item["currentAttemptId"] == response.json()["data"]["attemptId"]
        )

    surface_a_body, surface_a_run = ui_launch(
        "ui_surface", sourceRepositoryId="frontend", functionCaseIds=["C1"]
    )
    assert surface_a_run.status_code == 200, surface_a_run.text
    surface_a = ui_complete("ui_surface", surface_a_body, surface_a_run, "surface")
    ui_detail = api.get(
        f"{ui_base}/stages/ui_surface/candidates/{surface_a['candidateId']}", headers=headers
    )
    assert ui_detail.status_code == 200, ui_detail.text
    detail_source = ui_detail.json()["data"]["sourceInputs"]
    assert detail_source["repository"]["profileCandidateId"] == profile_candidate["candidateId"]
    assert detail_source["repository"]["commit"] == "commit-a"
    assert detail_source["cases"][0]["caseId"] == "C1"
    assert "connectionId" not in ui_detail.text and "cloneUrl" not in ui_detail.text
    surface_b_body, surface_b_run = ui_launch(
        "ui_surface", sourceRepositoryId="frontend", functionCaseIds=["C1"]
    )
    assert surface_b_run.status_code == 200, surface_b_run.text
    surface_b = ui_complete("ui_surface", surface_b_body, surface_b_run, "surface")
    ui_revision_body = {
        "expectedCandidateToken": surface_a["candidateToken"],
        "expectedAttemptId": surface_a["currentAttemptId"],
        "connectionId": "llm",
        "gitlabConnectionId": "ui-connection",
        "instruction": "补充错误提示",
        "requestId": str(uuid4()),
    }
    ui_revision = api.post(
        f"{ui_base}/stages/ui_surface/candidates/{surface_a['candidateId']}/revision",
        headers=headers,
        json=ui_revision_body,
    )
    assert ui_revision.status_code == 200, ui_revision.text
    revised_surface = ui_complete("ui_surface", ui_revision_body, ui_revision, "surface")
    assert revised_surface["derivedFromCandidateId"] == surface_a["candidateId"]
    revised_detail = api.get(
        f"{ui_base}/stages/ui_surface/candidates/{revised_surface['candidateId']}", headers=headers
    )
    assert revised_detail.json()["data"]["sourceInputs"]["repository"]["commit"] == "commit-a"

    async def attempts():
        async with api.app.state.test_sessions() as session:
            return [
                (
                    await session.scalar(
                        sa.select(AiGenerationAttempt).where(
                            AiGenerationAttempt.id == response.json()["data"]["attemptId"]
                        )
                    )
                ).input_snapshot_json
                for response in (surface_a_run, surface_b_run)
            ]

    frozen_a, frozen_b = asyncio.run(attempts())
    assert frozen_a["source"]["uiSourceBatchId"] != frozen_b["source"]["uiSourceBatchId"]
    assert frozen_a["source"]["sourceRepository"]["commit"] == "commit-a"
    assert frozen_a["source"]["bindings"][0]["connectionId"] == "ui-connection"

    async def worker_snapshot():
        async with api.app.state.test_sessions() as session:
            attempt = await session.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.id == surface_a_run.json()["data"]["attemptId"]
                )
            )
            task = await session.scalar(
                sa.select(AiGenerateTask).where(
                    AiGenerateTask.task_id == ui_config.json()["data"]["taskId"]
                )
            )
            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == surface_a_body["requestId"])
            )
            authority = DirectWorkerAuthority(
                attempt.stage_id,
                attempt.id,
                user["userId"],
                task,
                attempt.input_snapshot_json,
                None,
            )
            return worker_payloads(authority, queue, stage_name="ui_surface", lease_seconds=30)[1]

    worker_input = asyncio.run(worker_snapshot())
    assert worker_input["candidateProtocol"] == "single-current/1"
    assert worker_input["run"]["uiSourceBatchId"] == frozen_a["source"]["uiSourceBatchId"]
    assert worker_input["run"]["functionalCases"][0]["caseId"] == "C1"
    assert worker_input["run"]["sourceRepository"]["commit"] == "commit-a"
    assert "candidateInput" not in worker_input["run"]
    replay_surface = api.post(
        f"{ui_base}/stages/ui_surface/candidate-run", headers=headers, json=surface_a_body
    )
    assert replay_surface.status_code == 200 and replay_surface.json()["data"]["replayed"]

    async def set_surface_token(token):
        async with api.app.state.test_sessions() as session:
            await session.execute(
                sa.update(AiGenerationCandidate)
                .where(AiGenerationCandidate.candidate_id == surface_a["candidateId"])
                .values(candidate_token=token)
            )
            await session.commit()

    async def project_changes_surface(self, *args):
        await set_surface_token("changed-during-gitlab-read")
        return {
            "cloneUrl": "https://gitlab.example.com/team/frontend.git",
            "pathWithNamespace": "team/frontend",
        }

    monkeypatch.setattr(UiGenerationSourceService, "_project", project_changes_surface)
    _, changed_source = ui_launch(
        "ui_design",
        generationMode="trial",
        sourceSelections=[source(surface_a, "ui", "ui_surface")],
    )
    assert changed_source.status_code == 400
    assert changed_source.json()["data"]["reason"] == "concurrent_change"
    asyncio.run(set_surface_token(surface_a["candidateToken"]))
    monkeypatch.setattr(
        UiGenerationSourceService,
        "_project",
        AsyncMock(
            return_value={
                "cloneUrl": "https://gitlab.example.com/team/frontend.git",
                "pathWithNamespace": "team/frontend",
            }
        ),
    )

    async def set_case_title(title):
        async with api.app.state.test_sessions() as session:
            await session.execute(
                sa.update(FunctionTestCase)
                .where(FunctionTestCase.case_id == "C1")
                .values(title=title)
            )
            await session.commit()

    asyncio.run(set_case_title("功能用例已修改"))
    _, changed_case = ui_launch(
        "ui_design",
        generationMode="trial",
        sourceSelections=[source(surface_a, "ui", "ui_surface")],
    )
    assert changed_case.status_code == 400
    assert changed_case.json()["data"]["reason"] == "source_stale"
    asyncio.run(set_case_title("显示记录名称"))
    design_body, design_run = ui_launch(
        "ui_design",
        generationMode="trial",
        sourceSelections=[source(surface_a, "ui", "ui_surface")],
    )
    assert design_run.status_code == 200, design_run.text
    design_a = ui_complete("ui_design", design_body, design_run, "design")
    _, mixed = ui_launch(
        "ui_yaml",
        generationMode="trial",
        sourceSelections=[
            source(surface_b, "ui", "ui_surface"),
            source(design_a, "ui", "ui_design"),
        ],
    )
    assert mixed.status_code == 400, mixed.text
    assert mixed.json()["data"]["reason"] == "source_conflict"
    adopt(surface_a, "ui", "ui_surface")
    ui_current = api.get(f"{ui_base}/stages/ui_surface/current", headers=headers)
    assert (
        ui_current.json()["data"]["sourceInputs"]["sourceBatchId"] == detail_source["sourceBatchId"]
    )
    adopt(design_a, "ui", "ui_design")
    yaml_body, yaml_run = ui_launch("ui_yaml")
    assert yaml_run.status_code == 200, yaml_run.text
    yaml_candidate = ui_complete("ui_yaml", yaml_body, yaml_run, "draft", yaml=True)
    yaml_token = adopt(yaml_candidate, "ui", "ui_yaml")
    ui_preview = api.post(
        f"{ui_base}/stages/ui_yaml/current/import-preview",
        headers=headers,
        json={"expectedCurrentToken": yaml_token, "targetId": "ui-target-suite"},
    )
    assert ui_preview.status_code == 200, ui_preview.text
    preview_data = ui_preview.json()["data"]
    ui_import_body = {
        "expectedCurrentToken": yaml_token,
        "expectedLineageHash": preview_data["fullLineageHash"],
        "previewToken": preview_data["previewToken"],
        "targetId": "ui-target-suite",
        "requestId": str(uuid4()),
    }
    ui_import = api.post(
        f"{ui_base}/stages/ui_yaml/current/import", headers=headers, json=ui_import_body
    )
    assert ui_import.status_code == 200 and ui_import.json()["data"]["imported"], ui_import.text
    ui_retry = api.post(
        f"{ui_base}/stages/ui_yaml/current/import", headers=headers, json=ui_import_body
    )
    assert ui_retry.status_code == 200 and ui_retry.json()["data"]["replayed"], ui_retry.text

    async def sprint_id():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                sa.select(Requirement).where(Requirement.requirement_id == rid)
            )
            return row.sprint_id

    order = make_order(api, headers, asyncio.run(sprint_id()), name="candidate graph")
    case_id = imported.json()["data"]["changedCaseIds"][0]
    added = api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=headers, json={"caseIds": [case_id]}
    )
    assert added.status_code == 200, added.text
    graph = api.get(f"/v1/test-orders/{order['orderId']}/graph-input", headers=headers)
    assert graph.status_code == 200, graph.text
    assert (
        json.loads(graph.json()["data"]["requirements"][0]["requirement_content"])
        == material_artifact()
    )

    # Simulate another reviewer replacing the current token between the two
    # transactions. The review remains committed, but no continuation starts.
    point_url = bases["function"] + "/stages/case_names"
    point_current = api.get(point_url + "/current", headers=headers).json()["data"]
    continue_body = {
        "action": "adopt",
        "candidateId": points["candidateId"],
        "expectedCandidateToken": points["candidateToken"],
        "expectedAttemptId": points["currentAttemptId"],
        "expectedCurrentToken": point_current["currentToken"],
        "requestId": str(uuid4()),
        "continueAfter": True,
        "connectionId": "llm",
    }
    original_dispatch = CandidateDispatchApplication.run

    async def change_before_continuation(self, **kwargs):
        async with api.app.state.test_sessions() as session:
            await session.execute(
                sa.update(AiGenerationStageContent)
                .where(AiGenerationStageContent.source_candidate_id == points["candidateId"])
                .values(content_token="concurrent-replacement")
            )
            await session.commit()
        return await original_dispatch(self, **kwargs)

    with monkeypatch.context() as changes:
        changes.setattr(CandidateDispatchApplication, "run", change_before_continuation)
        raced = api.post(point_url + "/adoption", headers=headers, json=continue_body)
    assert raced.status_code == 200, raced.text
    assert raced.json()["data"]["continuationAttemptId"] is None
    assert "请刷新后重试" in raced.json()["data"]["continuationError"]
    raced_replay = api.post(point_url + "/adoption", headers=headers, json=continue_body)
    assert raced_replay.status_code == 200 and raced_replay.json()["data"]["replayed"]
    assert raced_replay.json()["data"]["continuationAttemptId"] is None
    assert "请刷新后重试" in raced_replay.json()["data"]["continuationError"]
    raced_current = api.get(point_url + "/current", headers=headers).json()["data"]
    assert raced_current["candidateId"] == points["candidateId"]
    assert raced_current["currentToken"] == "concurrent-replacement"

    # Retrying a successful review must not start another worker.
    continue_body.update(expectedCurrentToken=raced_current["currentToken"], requestId=str(uuid4()))
    continued = api.post(point_url + "/adoption", headers=headers, json=continue_body)
    assert continued.status_code == 200, continued.text
    continuation = continued.json()["data"]
    assert continuation["continuationAttemptId"] and not continuation["continuationError"]
    continued_again = api.post(point_url + "/adoption", headers=headers, json=continue_body)
    assert continued_again.status_code == 200, continued_again.text
    assert continued_again.json()["data"]["replayed"]
    assert (
        continued_again.json()["data"]["continuationAttemptId"]
        == continuation["continuationAttemptId"]
    )

    cleared_profile = api.post(
        profile_base + "/current/clear",
        headers=headers,
        json={
            "expectedCurrentToken": adopted_profile.json()["data"]["contentToken"],
            "requestId": str(uuid4()),
        },
    )
    assert cleared_profile.status_code == 200, cleared_profile.text
    old_replay = api.post(profile_base + "/current/adopt", headers=headers, json=profile_adopt)
    assert old_replay.status_code == 200 and old_replay.json()["data"]["replayed"]
    assert api.get(profile_base + "/current", headers=headers).json()["data"]["candidateId"] is None
    candidate_check_url = (
        f"{ui_base}/stages/ui_surface/candidates/{surface_a['candidateId']}/source-check"
    )
    candidate_check = {"expectedCandidateToken": surface_a["candidateToken"]}
    checked_frozen = api.post(candidate_check_url, headers=headers, json=candidate_check)
    assert checked_frozen.status_code == 200, checked_frozen.text
    assert checked_frozen.json()["data"]["pinnedCommit"] == "commit-a"
    assert checked_frozen.json()["data"]["currentCommit"] == "commit-b"
    assert checked_frozen.json()["data"]["changed"] is True
    stale_check = api.post(
        candidate_check_url, headers=headers, json={"expectedCandidateToken": "old-token"}
    )
    assert (
        stale_check.status_code == 400
        and stale_check.json()["data"]["reason"] == "concurrent_change"
    )
    _, outsider = account(api, "profile-outsider")
    assert api.post(candidate_check_url, headers=outsider, json=candidate_check).status_code == 403

    async def head_changes_candidate(self, *args):
        await set_surface_token("changed-during-head-check")
        return "commit-b"

    monkeypatch.setattr(UiGenerationSourceService, "resolve_latest_commit", head_changes_candidate)
    raced_check = api.post(candidate_check_url, headers=headers, json=candidate_check)
    assert (
        raced_check.status_code == 400
        and raced_check.json()["data"]["reason"] == "concurrent_change"
    )
