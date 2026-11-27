"""HTTP workflow from trial candidates to adoption and formal import."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from functools import partial
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
import yaml as yaml_module
from support.memory_storage import Storage
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

DOCUMENT = b"verified document"
CASES_YAML = "cases:\n  - case_id: graph-case\n    title: example\n"
GRAPH = {"schema_version": "2.0", "main_paths": [], "edges": []}
GITLAB_PROJECT = {
    "cloneUrl": "https://gitlab.example.com/team/frontend.git",
    "pathWithNamespace": "team/frontend",
}


async def with_session(app, action):
    """Await ``action`` with an application session; safe inside a running event loop."""
    async with app.state.test_sessions() as session:
        return await action(session)


def in_session(app, action):
    """``with_session`` for synchronous test code, on an event loop of its own."""
    return asyncio.run(with_session(app, action))


@pytest.fixture
def workflow(api, monkeypatch):  # noqa: F811
    """A requirement with a stored document and a model, and its two candidate chains started."""
    user, headers = account(api, "workflow-complete")
    pid = project(api, headers)
    rid = requirement(api, headers, pid)
    digest = sha256(DOCUMENT).hexdigest()
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=Storage(DOCUMENT))
    monkeypatch.setitem(api.app.dependency_overrides, get_file_service, lambda: files)

    async def seed(session):
        req = await session.scalar(sa.select(Requirement).where(Requirement.requirement_id == rid))
        req.document_type, req.document_file_id = "docx", "document"
        req.document_filename, req.document_hash = "requirement.docx", digest
        session.add(
            StoredFile(
                file_id="document",
                project_id=pid,
                uploaded_by=user["userId"],
                filename="requirement.docx",
                content_type="application/octet-stream",
                size=len(DOCUMENT),
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

    in_session(api.app, seed)
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
    return SimpleNamespace(
        api=api,
        headers=headers,
        user=user,
        pid=pid,
        rid=rid,
        files=files,
        bases=bases,
        profile_base=f"/v1/requirements/{rid}/repository-profile",
        ui_base=f"/v1/requirements/{rid}/generation/ui",
    )


def read(workflow, url, **kwargs):
    """``GET`` as the owner; returns the data of a successful response."""
    response = workflow.api.get(url, headers=workflow.headers, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def run_in_app(workflow, action):
    return in_session(workflow.api.app, action)


# ---- the function chain over HTTP ----


def launch(workflow, kind, stage, selections=None):
    """Run ``stage`` on ``selections`` as a trial, or in current mode without them."""
    body = {
        "connectionId": "llm",
        "requestId": str(uuid4()),
        "generationMode": "trial" if selections is not None else "current",
    }
    if selections is not None:
        body["sourceSelections"] = selections
    response = workflow.api.post(
        f"{workflow.bases[kind]}/stages/{stage}/candidate-run",
        headers=workflow.headers,
        json=body,
    )
    assert response.status_code == 200, response.text
    return body, response.json()["data"]


def complete(workflow, kind, stage_name, request, result, output, fmt="json"):
    """Let the worker complete the run with ``output``; returns the candidate it produced."""
    task_type = (
        "requirement_analysis" if kind == "requirement_analysis" else "functional_case_generate"
    )

    async def emit(session):
        stage = await session.scalar(
            sa.select(AiGenerationStage)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
            .where(
                AiGenerateTask.requirement_id == workflow.rid,
                AiGenerateTask.task_type == task_type,
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

    run_in_app(workflow, emit)
    candidates = read(workflow, f"{workflow.bases[kind]}/stages/{stage_name}/candidates")
    return next(
        item for item in candidates["items"] if item["currentAttemptId"] == result["attemptId"]
    )


def source(candidate, kind, stage):
    """Selection of ``candidate`` as a source of the next stage."""
    return {
        "chainKind": kind,
        "stage": stage,
        "sourceKind": "candidate",
        "candidateId": candidate["candidateId"],
        "snapshotId": candidate["snapshotId"],
        "expectedCandidateToken": candidate["candidateToken"],
    }


def adopt(workflow, candidate, kind, stage):
    """Check and adopt ``candidate`` into its stage; returns the content token of the slot."""
    url = f"{workflow.bases[kind]}/stages/{stage}"
    current = read(workflow, url + "/current")
    body = {
        "action": "adopt",
        "candidateId": candidate["candidateId"],
        "expectedCandidateToken": candidate["candidateToken"],
        "expectedAttemptId": candidate["currentAttemptId"],
        "expectedCurrentToken": current["currentToken"],
        "requestId": str(uuid4()),
    }
    preflight = workflow.api.post(url + "/adoption/check", headers=workflow.headers, json=body)
    assert preflight.status_code == 200 and preflight.json()["data"]["canAdopt"], preflight.text
    adopted = workflow.api.post(url + "/adoption", headers=workflow.headers, json=body)
    assert adopted.status_code == 200, adopted.text
    return adopted.json()["data"]["contentToken"]


def trial_points(workflow):
    """Extract the material, analyze it and name its test points, all as trials."""
    req, run = launch(workflow, "requirement_analysis", "extracting_text")
    material = complete(
        workflow, "requirement_analysis", "extracting_text", req, run, material_artifact()
    )
    req, run = launch(
        workflow,
        "function",
        "requirement_analysis",
        [source(material, "requirement_analysis", "extracting_text")],
    )
    analysis = complete(workflow, "function", "requirement_analysis", req, run, scope_artifact())
    req, run = launch(
        workflow,
        "function",
        "case_names",
        [source(analysis, "function", "requirement_analysis")],
    )
    points = complete(workflow, "function", "case_names", req, run, points_artifact())
    return SimpleNamespace(material=material, analysis=analysis, points=points)


def trial_cases(workflow, branch, points):
    """Write the detailed cases from the analysis and ``points`` as a trial."""
    req, run = launch(
        workflow,
        "function",
        "detailed_cases",
        [
            source(branch.analysis, "function", "requirement_analysis"),
            source(points, "function", "case_names"),
        ],
    )
    return complete(workflow, "function", "detailed_cases", req, run, CASES_YAML, "yaml")


def adopt_branch(workflow, branch):
    """Adopt the material, the analysis, the points and the cases of ``branch``.

    Returns the content token of the adopted cases.
    """
    adopt(workflow, branch.material, "requirement_analysis", "extracting_text")
    adopt(workflow, branch.analysis, "function", "requirement_analysis")
    adopt(workflow, branch.points, "function", "case_names")
    return adopt(workflow, branch.cases, "function", "detailed_cases")


def adopted_cases(workflow):
    """Generate the trial branch of the requirement and adopt all of it; returns branch, token."""
    branch = trial_points(workflow)
    branch.cases = trial_cases(workflow, branch, branch.points)
    return branch, adopt_branch(workflow, branch)


def points_revision(workflow, candidate, instruction="补充边界条件"):
    """URL and body of a revision of the case-names ``candidate``."""
    url = (
        workflow.bases["function"]
        + f"/stages/case_names/candidates/{candidate['candidateId']}/revision"
    )
    body = {
        "expectedCandidateToken": candidate["candidateToken"],
        "expectedAttemptId": candidate["currentAttemptId"],
        "connectionId": "llm",
        "instruction": instruction,
        "requestId": str(uuid4()),
    }
    return url, body


async def replace_document_row(session, workflow, content):
    """Replace the stored requirement document and its hash, as an editor would."""
    requirement_row = await session.scalar(
        sa.select(Requirement).where(Requirement.requirement_id == workflow.rid)
    )
    file_row = await session.scalar(sa.select(StoredFile).where(StoredFile.file_id == "document"))
    requirement_row.document_hash = sha256(content).hexdigest()
    file_row.sha256, file_row.size = sha256(content).hexdigest(), len(content)
    await session.commit()
    workflow.files.storage.data = content


def replace_document(workflow, content):
    run_in_app(workflow, partial(replace_document_row, workflow=workflow, content=content))


async def set_slot_token(session, source_candidate_id, token):
    """Replace the slot token of the stage whose source is ``source_candidate_id``."""
    await session.execute(
        sa.update(AiGenerationStageContent)
        .where(AiGenerationStageContent.source_candidate_id == source_candidate_id)
        .values(content_token=token)
    )
    await session.commit()


async def set_surface_token(session, candidate_id, token):
    """Replace the token of a UI surface candidate."""
    await session.execute(
        sa.update(AiGenerationCandidate)
        .where(AiGenerationCandidate.candidate_id == candidate_id)
        .values(candidate_token=token)
    )
    await session.commit()


async def set_case_title(session, title):
    """Edit the function case a UI surface is generated from."""
    await session.execute(
        sa.update(FunctionTestCase).where(FunctionTestCase.case_id == "C1").values(title=title)
    )
    await session.commit()


def project_read_that(workflow, action):
    """``_project`` replacement that runs ``action`` while the repository is being read."""

    async def resolve(*args):
        await with_session(workflow.api.app, action)
        return dict(GITLAB_PROJECT)

    return resolve


def head_read_that(workflow, action):
    """``resolve_latest_commit`` replacement that runs ``action`` while the head is checked."""

    async def resolve(*args):
        await with_session(workflow.api.app, action)
        return "commit-b"

    return resolve


def requirement_sprint(workflow):
    async def load(session):
        row = await session.scalar(
            sa.select(Requirement).where(Requirement.requirement_id == workflow.rid)
        )
        return row.sprint_id

    return run_in_app(workflow, load)


def imported_case_count(workflow):
    async def count(session):
        return await session.scalar(
            sa.select(sa.func.count())
            .select_from(FunctionTestCase)
            .where(FunctionTestCase.title == "example")
        )

    return run_in_app(workflow, count)


# ---- the repository profile ----


async def profile_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
    """Profile of a run: one frontend repository reached through a private GitLab connection."""
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


def run_profile(workflow, monkeypatch):
    """Create and run a repository-profile task and complete it; returns the candidates."""
    monkeypatch.setattr(RepositoryProfileService, "build_snapshot", profile_snapshot)
    task = workflow.api.post(
        f"/v1/projects/{workflow.pid}/repository-profile-tasks",
        headers=workflow.headers,
        json={"requirementId": workflow.rid},
    )
    assert task.status_code == 200, task.text
    run = workflow.api.post(
        f"/v1/repository-profile-tasks/{task.json()['data']['taskId']}/run",
        headers=workflow.headers,
        json={"connectionId": "llm"},
    )
    assert run.status_code == 200, run.text

    async def complete_profile(session):
        attempt = await session.scalar(
            sa.select(AiGenerationAttempt).where(
                AiGenerationAttempt.execution_id == run.json()["data"]["runId"]
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

    run_in_app(workflow, complete_profile)
    return read(workflow, workflow.profile_base + "/candidates")


def profile_adoption(candidate, expected_current_token):
    return {
        "action": "adopt",
        "candidateId": candidate["candidateId"],
        "expectedCandidateToken": candidate["candidateToken"],
        "expectedAttemptId": candidate["currentAttemptId"],
        "expectedCurrentToken": expected_current_token,
        "requestId": str(uuid4()),
    }


def adopt_profile(workflow, candidate):
    """Adopt the profile ``candidate`` while its slot is empty; returns the request and result."""
    current = read(workflow, workflow.profile_base + "/current")
    body = profile_adoption(candidate, current["currentToken"])
    response = workflow.api.post(
        workflow.profile_base + "/current/adopt", headers=workflow.headers, json=body
    )
    assert response.status_code == 200, response.text
    return body, response.json()["data"]


def source_options(workflow):
    """Raw response of the UI source options, to check what they expose."""
    return workflow.api.get(
        f"/v1/requirements/{workflow.rid}/generation/ui/source-options", headers=workflow.headers
    )


def add_viewer(workflow):
    """Give a viewer read access to the project; returns the viewer's headers."""
    _, viewer = account(workflow.api, "profile-viewer")
    added = workflow.api.post(
        f"/v1/projects/{workflow.pid}/members",
        headers=workflow.headers,
        json={"name": "profile-viewer", "role": "viewer"},
    )
    assert added.status_code == 200, added.text
    return viewer


# ---- UI generation ----


def patch_ui_source(monkeypatch):
    """GitLab lookups of UI generation resolve to one frontend repository at ``commit-b``."""
    monkeypatch.setattr(
        UiGenerationSourceService,
        "resolve_binding_access",
        AsyncMock(
            return_value=RepoGitlabAccess("ui-connection", "https://gitlab.example.com", "test")
        ),
    )
    monkeypatch.setattr(
        UiGenerationSourceService, "_project", AsyncMock(return_value=dict(GITLAB_PROJECT))
    )
    monkeypatch.setattr(
        UiGenerationSourceService, "resolve_latest_commit", AsyncMock(return_value="commit-b")
    )


async def seed_ui_source(session, workflow):
    """The frontend repository and the requirement case UI generation works from."""
    session.add(
        SoftwareRepository(
            software_repository_id="frontend-binding",
            project_id=workflow.pid,
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
            created_by_user_id=workflow.user["userId"],
        )
    )
    session.add(
        FunctionTestSuite(suite_id="ui-source-suite", requirement_id=workflow.rid, name="功能")
    )
    session.add(
        UiTestSuite(
            suite_id="ui-target-suite",
            project_id=workflow.pid,
            requirement_id=workflow.rid,
            name="UI",
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


def ui_ready(workflow, monkeypatch):
    """Everything UI generation needs: adopted cases and profile, a repository and a UI chain.

    Returns the adopted profile candidate and the adoption result.
    """
    adopted_cases(workflow)
    candidate = run_profile(workflow, monkeypatch)["items"][0]
    _, adoption = adopt_profile(workflow, candidate)
    patch_ui_source(monkeypatch)
    run_in_app(workflow, partial(seed_ui_source, workflow=workflow))
    config = workflow.api.post(
        f"/v1/requirements/{workflow.rid}/design/ui/configuration",
        headers=workflow.headers,
        json={},
    )
    assert config.status_code == 200, config.text
    initialized = workflow.api.post(
        workflow.ui_base + "/candidate-chain",
        headers=workflow.headers,
        json={"taskId": config.json()["data"]["taskId"]},
    )
    assert initialized.status_code == 200, initialized.text
    workflow.ui_task_id = config.json()["data"]["taskId"]
    workflow.bases["ui"] = workflow.ui_base
    return SimpleNamespace(candidate=candidate, adoption=adoption, viewer=add_viewer(workflow))


def ui_launch(workflow, stage, **extra):
    """Run a UI stage as the owner; returns the body and the raw response."""
    body = {"connectionId": "llm", "requestId": str(uuid4()), **extra}
    response = workflow.api.post(
        f"{workflow.ui_base}/stages/{stage}/candidate-run", headers=workflow.headers, json=body
    )
    return body, response


def ui_complete(workflow, stage, body, response, fixture, *, yaml=False):
    """Validate ``fixture`` against the run, complete it and return its UI candidate."""
    if yaml:
        content = yaml_module.safe_load((UI_FIXTURES / (fixture + ".yaml")).read_text())
        content[0]["stepsJson"][0].update(locatorType="css", locatorValue="#name")
        content[0]["stepsJson"][0].pop("missingFields", None)
        output = yaml_module.safe_dump(content, allow_unicode=True)
    else:
        output = json.dumps(ui_fixture(fixture), ensure_ascii=False)

    async def emit(session):
        attempt = await session.get(AiGenerationAttempt, response.json()["data"]["attemptId"])
        validate_ui_output(
            SimpleNamespace(snapshot_json=attempt.input_snapshot_json["source"]), stage, output
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

    run_in_app(workflow, emit)
    listing = read(workflow, f"{workflow.ui_base}/stages/{stage}/candidates")
    return next(
        item
        for item in listing["items"]
        if item["currentAttemptId"] == response.json()["data"]["attemptId"]
    )


def ui_surface(workflow):
    """Run the UI surface stage over case ``C1`` and complete it; returns the run."""
    body, response = ui_launch(
        workflow, "ui_surface", sourceRepositoryId="frontend", functionCaseIds=["C1"]
    )
    assert response.status_code == 200, response.text
    return SimpleNamespace(
        body=body,
        response=response,
        candidate=ui_complete(workflow, "ui_surface", body, response, "surface"),
    )


def surface_detail(workflow, candidate):
    """Raw detail response of a UI surface candidate."""
    return workflow.api.get(
        f"{workflow.ui_base}/stages/ui_surface/candidates/{candidate['candidateId']}",
        headers=workflow.headers,
    )


def frozen_source(workflow, run):
    """Frozen ``source`` input of a UI run."""

    async def load(session):
        attempt = await session.get(AiGenerationAttempt, run.response.json()["data"]["attemptId"])
        return attempt.input_snapshot_json["source"]

    return run_in_app(workflow, load)


def attempt_snapshot(workflow, result):
    """Frozen input snapshot of the attempt behind a chain run's ``result``."""

    async def load(session):
        attempt = await session.get(AiGenerationAttempt, result["attemptId"])
        return attempt.input_snapshot_json

    return run_in_app(workflow, load)


def worker_snapshot(workflow, run):
    """What the worker receives for a UI surface run."""

    async def load(session):
        attempt = await session.get(AiGenerationAttempt, run.response.json()["data"]["attemptId"])
        task = await session.scalar(
            sa.select(AiGenerateTask).where(AiGenerateTask.task_id == workflow.ui_task_id)
        )
        queue = await session.scalar(
            sa.select(WorkerTask).where(WorkerTask.task_id == run.body["requestId"])
        )
        authority = DirectWorkerAuthority(
            attempt.stage_id,
            attempt.id,
            workflow.user["userId"],
            task,
            attempt.input_snapshot_json,
            None,
        )
        return worker_payloads(authority, queue, stage_name="ui_surface", lease_seconds=30)[1]

    return run_in_app(workflow, load)


# ---- tests ----


def test_candidates_can_be_revised_in_sequence_and_derived(workflow):
    branch = trial_points(workflow)
    points = branch.points
    detail = read(
        workflow,
        f"{workflow.bases['function']}/stages/case_names/candidates/{points['candidateId']}",
    )
    url, body = points_revision(workflow, points)

    stale = workflow.api.post(
        url,
        headers=workflow.headers,
        json={**body, "expectedCandidateToken": "outdated", "requestId": str(uuid4())},
    )
    revision = workflow.api.post(url, headers=workflow.headers, json=body)
    replay = workflow.api.post(url, headers=workflow.headers, json=body)
    revised_points = complete(
        workflow, "function", "case_names", body, revision.json()["data"], points_artifact()
    )
    second_url, second_body = points_revision(workflow, revised_points, "再补充异常场景")
    second_revision = workflow.api.post(second_url, headers=workflow.headers, json=second_body)
    revised_again = complete(
        workflow,
        "function",
        "case_names",
        second_body,
        second_revision.json()["data"],
        points_artifact(),
    )
    revised_detail = read(
        workflow,
        f"{workflow.bases['function']}/stages/case_names/candidates/{revised_again['candidateId']}",
    )
    manual = workflow.api.post(
        f"{workflow.bases['function']}/stages/case_names/candidates/{revised_again['candidateId']}/derive",
        headers=workflow.headers,
        json={
            "expectedCandidateToken": revised_again["candidateToken"],
            "expectedAttemptId": revised_again["currentAttemptId"],
            "content": revised_detail["content"],
            "requestId": str(uuid4()),
        },
    )
    req, run = launch(
        workflow,
        "function",
        "detailed_cases",
        [
            source(branch.analysis, "function", "requirement_analysis"),
            source(manual.json()["data"], "function", "case_names"),
        ],
    )
    revised_cases = complete(
        workflow,
        "function",
        "detailed_cases",
        req,
        run,
        "cases:\n  - case_id: revised-case\n    title: revised\n",
        "yaml",
    )

    assert json.loads(detail["materialContent"]) == material_artifact()
    assert stale.status_code == 400 and stale.json()["data"]["reason"] == "concurrent_change"
    assert revision.status_code == 200, revision.text
    assert replay.status_code == 200 and replay.json()["data"]["replayed"]
    assert revised_points["derivedFromCandidateId"] == points["candidateId"]
    assert second_revision.status_code == 200, second_revision.text
    assert revised_again["derivedFromCandidateId"] == revised_points["candidateId"]
    assert manual.status_code == 200, manual.text
    assert revised_cases["generationMode"] == "trial"


def test_adopted_candidates_expose_their_material_and_sources(workflow):
    branch = trial_points(workflow)
    branch.cases = trial_cases(workflow, branch, branch.points)
    adopt(workflow, branch.material, "requirement_analysis", "extracting_text")
    options = source_options(workflow)
    adopt(workflow, branch.analysis, "function", "requirement_analysis")
    adopt(workflow, branch.points, "function", "case_names")
    current_points = read(workflow, f"{workflow.bases['function']}/stages/case_names/current")
    adopt(workflow, branch.cases, "function", "detailed_cases")

    leaf = read(workflow, f"{workflow.bases['function']}/stages/detailed_cases/current")

    assert options.status_code == 200, options.text
    assert options.json()["data"]["currentProfile"] is None
    assert json.loads(current_points["materialContent"]) == material_artifact()
    assert leaf["sourceAttemptId"] == branch.cases["currentAttemptId"]
    assert {
        (item["chainKind"], item["stage"], item["candidateId"], item["direct"])
        for item in leaf["basisSources"]
    } == {
        ("requirement_analysis", "extracting_text", branch.material["candidateId"], False),
        ("function", "requirement_analysis", branch.analysis["candidateId"], True),
        ("function", "case_names", branch.points["candidateId"], True),
    }


def test_complete_cases_freeze_the_adopted_history_verification(workflow):
    """ADR 0038: the adopted history verification is a direct upstream of the complete cases."""
    branch = trial_points(workflow)
    adopt(workflow, branch.material, "requirement_analysis", "extracting_text")

    relation_req, relation_run = launch(
        workflow, "requirement_analysis", "historical_requirement_relations"
    )
    history_source = json.loads(attempt_snapshot(workflow, relation_run)["source"]["sourceContent"])
    relation = complete(
        workflow,
        "requirement_analysis",
        "historical_requirement_relations",
        relation_req,
        relation_run,
        {
            "schemaVersion": "0.1",
            "artifactType": "historical_requirement_relation_analysis",
            "requirementId": workflow.rid,
            "materialSnapshotId": history_source["currentRequirement"]["materialSnapshotId"],
            "relations": [],
            "openQuestions": [],
        },
    )
    adopt(workflow, relation, "requirement_analysis", "historical_requirement_relations")

    history_req, history_run = launch(
        workflow, "requirement_analysis", "historical_test_case_verification"
    )
    history_input = json.loads(attempt_snapshot(workflow, history_run)["source"]["sourceContent"])
    history_result = {
        **verification_run_header(VERIFICATION_RUN_RESULT, history_input),
        "batches": [],
    }
    verification = complete(
        workflow,
        "requirement_analysis",
        "historical_test_case_verification",
        history_req,
        history_run,
        history_result,
    )
    adopt(workflow, verification, "requirement_analysis", "historical_test_case_verification")

    cases_req, cases_run = launch(
        workflow,
        "function",
        "detailed_cases",
        [
            source(branch.analysis, "function", "requirement_analysis"),
            source(branch.points, "function", "case_names"),
        ],
    )
    planning = attempt_snapshot(workflow, cases_run)["config"]["historyCasePlanning"]
    assert planning["verification"] == history_result
    assert json.loads(planning["input"]) == history_input

    # Planning is frozen, so the artifact names its historical findings even when none is reused.
    cases = complete(
        workflow,
        "function",
        "detailed_cases",
        cases_req,
        cases_run,
        {**yaml_module.safe_load(CASES_YAML), "historicalCaseFindings": []},
    )
    adopt(workflow, branch.analysis, "function", "requirement_analysis")
    adopt(workflow, branch.points, "function", "case_names")
    adopt(workflow, cases, "function", "detailed_cases")

    leaf = read(workflow, f"{workflow.bases['function']}/stages/detailed_cases/current")
    assert leaf["sourceAttemptId"] == cases["currentAttemptId"]
    assert {
        (item["chainKind"], item["stage"], item["candidateId"], item["direct"])
        for item in leaf["basisSources"]
    } == {
        ("requirement_analysis", "extracting_text", branch.material["candidateId"], False),
        ("function", "requirement_analysis", branch.analysis["candidateId"], True),
        ("function", "case_names", branch.points["candidateId"], True),
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


def test_a_replaced_document_makes_revisions_of_a_candidate_stale(workflow):
    branch, _ = adopted_cases(workflow)
    url, body = points_revision(workflow, branch.points)
    replace_document(workflow, b"changed requirement")

    stale = workflow.api.post(
        url, headers=workflow.headers, json={**body, "requestId": str(uuid4())}
    )

    assert stale.status_code == 400 and stale.json()["data"]["reason"] == "source_stale"


def test_the_relation_graph_of_adopted_cases_runs_once_and_completes(workflow):
    _, token = adopted_cases(workflow)
    graph_url = workflow.bases["function"] + "/relations/current"
    graph_body = {"currentToken": token, "connectionId": "llm", "requestId": str(uuid4())}

    empty = read(workflow, graph_url, params={"currentToken": token})
    run = workflow.api.post(graph_url + "/run", headers=workflow.headers, json=graph_body)
    replay = workflow.api.post(graph_url + "/run", headers=workflow.headers, json=graph_body)

    async def complete_graph(session):
        attempt = await session.get(AiGenerationAttempt, run.json()["data"]["attemptId"])
        await StageWorkerTransitions(session).completed(
            attempt.stage_id,
            attempt.id,
            graph_body["requestId"],
            content=json.dumps(GRAPH),
            output_format="json",
            output_context=None,
        )
        await session.commit()

    run_in_app(workflow, complete_graph)
    current = read(workflow, graph_url, params={"currentToken": token})

    assert empty["status"] == "not_started"
    assert run.status_code == 200 and not run.json()["data"]["replayed"]
    assert replay.status_code == 200 and replay.json()["data"]["replayed"]
    assert current["status"] == "success"


def test_adopted_cases_import_once_and_reach_test_orders(workflow):
    branch, token = adopted_cases(workflow)
    url = workflow.bases["function"] + "/stages/detailed_cases/current"
    preview = workflow.api.post(
        url + "/import-preview", headers=workflow.headers, json={"expectedCurrentToken": token}
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    body = {
        "expectedCurrentToken": token,
        "expectedLineageHash": data["fullLineageHash"],
        "previewToken": data["previewToken"],
        "requestId": str(uuid4()),
    }

    imported = workflow.api.post(url + "/import", headers=workflow.headers, json=body)
    history = read(
        workflow,
        f"/v1/requirements/{workflow.rid}/design/function/runs",
        params={"pipelineFilter": "imported"},
    )
    replay = workflow.api.post(url + "/import", headers=workflow.headers, json=body)
    chain = read(workflow, workflow.bases["function"])
    order = make_order(
        workflow.api, workflow.headers, requirement_sprint(workflow), name="candidate graph"
    )
    added = workflow.api.post(
        f"/v1/test-orders/{order['orderId']}/cases",
        headers=workflow.headers,
        json={"caseIds": [imported.json()["data"]["changedCaseIds"][0]]},
    )
    graph = read(workflow, f"/v1/test-orders/{order['orderId']}/graph-input")

    imported_run = next(
        item for item in history["items"] if item["runId"] == branch.cases["currentAttemptId"]
    )
    final_stage = next(item for item in chain["stages"] if item["stage"] == "detailed_cases")
    assert imported.status_code == 200 and imported.json()["data"]["imported"], imported.text
    assert imported_run["reviewStatus"] == "approved"
    assert imported_run["importStatus"] == "imported"
    assert imported_run["importedTargets"]
    assert replay.status_code == 200 and replay.json()["data"]["replayed"]
    assert chain["candidateMode"] is True
    assert final_stage["state"] == "approved"
    assert not {"versions", "latestVersion", "draft"} & final_stage.keys()
    assert imported_case_count(workflow) == 1
    assert added.status_code == 200, added.text
    assert json.loads(graph["requirements"][0]["requirement_content"]) == material_artifact()


def test_a_profile_run_leaves_an_unadopted_candidate_that_viewers_can_only_read(
    workflow, monkeypatch
):
    branch, token = adopted_cases(workflow)
    candidates = run_profile(workflow, monkeypatch)
    candidate = candidates["items"][0]
    viewer = add_viewer(workflow)
    current = read(workflow, workflow.profile_base + "/current")
    options = source_options(workflow)
    detail = read(workflow, f"{workflow.profile_base}/candidates/{candidate['candidateId']}")
    revision_url, revision_body = points_revision(workflow, branch.points)
    graph_url = workflow.bases["function"] + "/relations/current"
    refused = [
        workflow.api.post(
            revision_url,
            headers=viewer,
            json={**revision_body, "requestId": str(uuid4())},
        ).status_code,
        workflow.api.post(
            graph_url + "/run",
            headers=viewer,
            json={"currentToken": token, "connectionId": "llm", "requestId": str(uuid4())},
        ).status_code,
        workflow.api.post(
            workflow.profile_base + "/current/adopt",
            headers=viewer,
            json=profile_adoption(candidate, current["currentToken"]),
        ).status_code,
    ]
    readable = [
        workflow.api.get(graph_url, headers=viewer, params={"currentToken": token}).status_code,
        workflow.api.get(workflow.profile_base + "/candidates", headers=viewer).status_code,
    ]

    assert current["candidateId"] is None
    assert candidates["total"] == 1
    assert options.status_code == 200, options.text
    assert options.json()["data"]["currentProfile"] is None
    assert json.loads(detail["content"])["overallSummary"] == "profile"
    assert refused == [403, 403, 403]
    assert readable == [200, 200]


def test_the_adopted_profile_feeds_ui_sources_until_it_is_cleared(workflow, monkeypatch):
    adopted_cases(workflow)
    candidate = run_profile(workflow, monkeypatch)["items"][0]
    request, adoption = adopt_profile(workflow, candidate)
    patch_ui_source(monkeypatch)
    check_url = f"/v1/requirements/{workflow.rid}/generation/ui/source-check"

    again = workflow.api.post(
        workflow.profile_base + "/current/adopt", headers=workflow.headers, json=request
    )
    options = source_options(workflow)
    checked = workflow.api.post(
        check_url,
        headers=workflow.headers,
        json={
            "profileCandidateId": candidate["candidateId"],
            "repositoryId": "frontend",
            "pinnedCommit": "commit-a",
        },
    )
    blocked = workflow.api.post(
        check_url,
        headers=workflow.headers,
        json={
            "profileCandidateId": "old-profile",
            "repositoryId": "frontend",
            "pinnedCommit": "commit-a",
        },
    )
    cleared = workflow.api.post(
        workflow.profile_base + "/current/clear",
        headers=workflow.headers,
        json={"expectedCurrentToken": adoption["contentToken"], "requestId": str(uuid4())},
    )
    old_replay = workflow.api.post(
        workflow.profile_base + "/current/adopt", headers=workflow.headers, json=request
    )

    assert again.status_code == 200 and again.json()["data"]["replayed"]
    assert options.status_code == 200, options.text
    assert options.json()["data"]["currentProfile"]["candidateId"] == candidate["candidateId"]
    assert options.json()["data"]["currentProfile"]["repositories"][0]["commit"] == "commit-a"
    assert "private.example" not in options.text and "private-connection" not in options.text
    assert checked.status_code == 200 and checked.json()["data"]["changed"]
    assert blocked.status_code == 400
    assert cleared.status_code == 200, cleared.text
    assert old_replay.status_code == 200 and old_replay.json()["data"]["replayed"]
    assert read(workflow, workflow.profile_base + "/current")["candidateId"] is None


def test_ui_surface_launch_validates_its_profile_repository_and_actor(workflow, monkeypatch):
    ready = ui_ready(workflow, monkeypatch)

    _, missing_repository = ui_launch(workflow, "ui_surface", functionCaseIds=["C1"])
    _, stale_profile = ui_launch(
        workflow,
        "ui_surface",
        sourceRepositoryId="frontend",
        sourceProfileCandidateId="old-profile",
        functionCaseIds=["C1"],
    )
    unauthorized = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_surface/candidate-run",
        headers=ready.viewer,
        json={
            "connectionId": "llm",
            "sourceRepositoryId": "frontend",
            "functionCaseIds": ["C1"],
        },
    )
    monkeypatch.setattr(
        UiGenerationSourceService,
        "_project",
        project_read_that(
            workflow,
            partial(
                set_slot_token,
                source_candidate_id=ready.candidate["candidateId"],
                token="changed-during-gitlab-read",
            ),
        ),
    )
    _, raced = ui_launch(
        workflow, "ui_surface", sourceRepositoryId="frontend", functionCaseIds=["C1"]
    )

    assert missing_repository.status_code == 400
    assert stale_profile.status_code == 400
    assert stale_profile.json()["data"]["reason"] == "concurrent_change"
    assert unauthorized.status_code == 403
    assert raced.status_code == 400 and raced.json()["data"]["reason"] == "concurrent_change"


def test_ui_surfaces_freeze_their_sources_replay_and_can_be_revised(workflow, monkeypatch):
    ready = ui_ready(workflow, monkeypatch)
    first, second = ui_surface(workflow), ui_surface(workflow)
    surface_a = first.candidate

    detail = surface_detail(workflow, surface_a)
    revision_body = {
        "expectedCandidateToken": surface_a["candidateToken"],
        "expectedAttemptId": surface_a["currentAttemptId"],
        "connectionId": "llm",
        "gitlabConnectionId": "ui-connection",
        "instruction": "补充错误提示",
        "requestId": str(uuid4()),
    }
    revision = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_surface/candidates/{surface_a['candidateId']}/revision",
        headers=workflow.headers,
        json=revision_body,
    )
    revised_surface = ui_complete(workflow, "ui_surface", revision_body, revision, "surface")
    revised_detail = read(
        workflow,
        f"{workflow.ui_base}/stages/ui_surface/candidates/{revised_surface['candidateId']}",
    )
    frozen_a = frozen_source(workflow, first)
    frozen_b = frozen_source(workflow, second)
    replay = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_surface/candidate-run",
        headers=workflow.headers,
        json=first.body,
    )
    worker_input = worker_snapshot(workflow, first)

    assert detail.status_code == 200, detail.text
    detail_source = detail.json()["data"]["sourceInputs"]
    assert detail_source["repository"]["profileCandidateId"] == ready.candidate["candidateId"]
    assert detail_source["repository"]["commit"] == "commit-a"
    assert detail_source["cases"][0]["caseId"] == "C1"
    assert "connectionId" not in detail.text and "cloneUrl" not in detail.text
    assert revision.status_code == 200, revision.text
    assert revised_surface["derivedFromCandidateId"] == surface_a["candidateId"]
    assert revised_detail["sourceInputs"]["repository"]["commit"] == "commit-a"
    assert frozen_a["uiSourceBatchId"] != frozen_b["uiSourceBatchId"]
    assert frozen_a["sourceRepository"]["commit"] == "commit-a"
    assert frozen_a["bindings"][0]["connectionId"] == "ui-connection"
    assert replay.status_code == 200 and replay.json()["data"]["replayed"]
    assert worker_input["candidateProtocol"] == "single-current/1"
    assert worker_input["run"]["uiSourceBatchId"] == frozen_a["uiSourceBatchId"]
    assert worker_input["run"]["functionalCases"][0]["caseId"] == "C1"
    assert worker_input["run"]["sourceRepository"]["commit"] == "commit-a"
    assert "candidateInput" not in worker_input["run"]


def test_ui_design_validates_its_sources(workflow, monkeypatch):
    ui_ready(workflow, monkeypatch)
    first, second = ui_surface(workflow), ui_surface(workflow)
    surface_a = first.candidate
    design = {
        "generationMode": "trial",
        "sourceSelections": [source(surface_a, "ui", "ui_surface")],
    }

    monkeypatch.setattr(
        UiGenerationSourceService,
        "_project",
        project_read_that(
            workflow,
            partial(
                set_surface_token,
                candidate_id=surface_a["candidateId"],
                token="changed-during-gitlab-read",
            ),
        ),
    )
    _, changed_source = ui_launch(workflow, "ui_design", **design)
    monkeypatch.setattr(
        UiGenerationSourceService, "_project", AsyncMock(return_value=dict(GITLAB_PROJECT))
    )
    run_in_app(
        workflow,
        partial(
            set_surface_token,
            candidate_id=surface_a["candidateId"],
            token=surface_a["candidateToken"],
        ),
    )
    run_in_app(workflow, partial(set_case_title, title="功能用例已修改"))
    _, changed_case = ui_launch(workflow, "ui_design", **design)
    run_in_app(workflow, partial(set_case_title, title="显示记录名称"))
    design_body, design_run = ui_launch(workflow, "ui_design", **design)
    design_a = ui_complete(workflow, "ui_design", design_body, design_run, "design")
    _, mixed = ui_launch(
        workflow,
        "ui_yaml",
        generationMode="trial",
        sourceSelections=[
            source(second.candidate, "ui", "ui_surface"),
            source(design_a, "ui", "ui_design"),
        ],
    )

    assert changed_source.status_code == 400
    assert changed_source.json()["data"]["reason"] == "concurrent_change"
    assert changed_case.status_code == 400
    assert changed_case.json()["data"]["reason"] == "source_stale"
    assert design_run.status_code == 200, design_run.text
    assert mixed.status_code == 400, mixed.text
    assert mixed.json()["data"]["reason"] == "source_conflict"


def test_ui_candidates_can_be_adopted_and_imported(workflow, monkeypatch):
    ui_ready(workflow, monkeypatch)
    surface = ui_surface(workflow)
    design_body, design_run = ui_launch(
        workflow,
        "ui_design",
        generationMode="trial",
        sourceSelections=[source(surface.candidate, "ui", "ui_surface")],
    )
    design_a = ui_complete(workflow, "ui_design", design_body, design_run, "design")
    detail_source = surface_detail(workflow, surface.candidate).json()["data"]["sourceInputs"]

    adopt(workflow, surface.candidate, "ui", "ui_surface")
    current = read(workflow, f"{workflow.ui_base}/stages/ui_surface/current")
    adopt(workflow, design_a, "ui", "ui_design")
    yaml_body, yaml_run = ui_launch(workflow, "ui_yaml")
    yaml_candidate = ui_complete(workflow, "ui_yaml", yaml_body, yaml_run, "draft", yaml=True)
    yaml_token = adopt(workflow, yaml_candidate, "ui", "ui_yaml")
    preview = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_yaml/current/import-preview",
        headers=workflow.headers,
        json={"expectedCurrentToken": yaml_token, "targetId": "ui-target-suite"},
    )
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    body = {
        "expectedCurrentToken": yaml_token,
        "expectedLineageHash": preview_data["fullLineageHash"],
        "previewToken": preview_data["previewToken"],
        "targetId": "ui-target-suite",
        "requestId": str(uuid4()),
    }

    imported = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_yaml/current/import", headers=workflow.headers, json=body
    )
    retry = workflow.api.post(
        f"{workflow.ui_base}/stages/ui_yaml/current/import", headers=workflow.headers, json=body
    )

    assert yaml_run.status_code == 200, yaml_run.text
    assert current["sourceInputs"]["sourceBatchId"] == detail_source["sourceBatchId"]
    assert imported.status_code == 200 and imported.json()["data"]["imported"], imported.text
    assert retry.status_code == 200 and retry.json()["data"]["replayed"], retry.text


def test_adoption_continuation_survives_a_concurrent_replacement(workflow, monkeypatch):
    branch, _ = adopted_cases(workflow)
    point_url = workflow.bases["function"] + "/stages/case_names"
    point_current = read(workflow, point_url + "/current")
    continue_body = {
        "action": "adopt",
        "candidateId": branch.points["candidateId"],
        "expectedCandidateToken": branch.points["candidateToken"],
        "expectedAttemptId": branch.points["currentAttemptId"],
        "expectedCurrentToken": point_current["currentToken"],
        "requestId": str(uuid4()),
        "continueAfter": True,
        "connectionId": "llm",
    }
    original_dispatch = CandidateDispatchApplication.run

    async def replace_then_dispatch(self, **kwargs):
        # Another writer replaces the token between the review and its continuation.
        await with_session(
            workflow.api.app,
            partial(
                set_slot_token,
                source_candidate_id=branch.points["candidateId"],
                token="concurrent-replacement",
            ),
        )
        return await original_dispatch(self, **kwargs)

    with monkeypatch.context() as changes:
        changes.setattr(CandidateDispatchApplication, "run", replace_then_dispatch)
        raced = workflow.api.post(
            point_url + "/adoption", headers=workflow.headers, json=continue_body
        )
    raced_replay = workflow.api.post(
        point_url + "/adoption", headers=workflow.headers, json=continue_body
    )
    raced_current = read(workflow, point_url + "/current")
    # Retrying a successful review must not start another worker.
    continue_body.update(expectedCurrentToken=raced_current["currentToken"], requestId=str(uuid4()))

    continued = workflow.api.post(
        point_url + "/adoption", headers=workflow.headers, json=continue_body
    )
    continued_again = workflow.api.post(
        point_url + "/adoption", headers=workflow.headers, json=continue_body
    )
    continuation = continued.json()["data"]

    assert raced.status_code == 200, raced.text
    assert raced.json()["data"]["continuationAttemptId"] is None
    assert "请刷新后重试" in raced.json()["data"]["continuationError"]
    assert raced_replay.status_code == 200 and raced_replay.json()["data"]["replayed"]
    assert raced_replay.json()["data"]["continuationAttemptId"] is None
    assert "请刷新后重试" in raced_replay.json()["data"]["continuationError"]
    assert raced_current["candidateId"] == branch.points["candidateId"]
    assert raced_current["currentToken"] == "concurrent-replacement"
    assert continued.status_code == 200, continued.text
    assert continuation["continuationAttemptId"] and not continuation["continuationError"]
    assert continued_again.status_code == 200, continued_again.text
    assert continued_again.json()["data"]["replayed"]
    assert (
        continued_again.json()["data"]["continuationAttemptId"]
        == continuation["continuationAttemptId"]
    )


def test_candidate_source_check_detects_commit_and_token_changes(workflow, monkeypatch):
    ui_ready(workflow, monkeypatch)
    surface = ui_surface(workflow).candidate
    url = f"{workflow.ui_base}/stages/ui_surface/candidates/{surface['candidateId']}/source-check"
    candidate_check = {"expectedCandidateToken": surface["candidateToken"]}
    _, outsider = account(workflow.api, "profile-outsider")

    checked = workflow.api.post(url, headers=workflow.headers, json=candidate_check)
    stale = workflow.api.post(
        url, headers=workflow.headers, json={"expectedCandidateToken": "old-token"}
    )
    refused = workflow.api.post(url, headers=outsider, json=candidate_check)
    monkeypatch.setattr(
        UiGenerationSourceService,
        "resolve_latest_commit",
        head_read_that(
            workflow,
            partial(
                set_surface_token,
                candidate_id=surface["candidateId"],
                token="changed-during-head-check",
            ),
        ),
    )
    raced = workflow.api.post(url, headers=workflow.headers, json=candidate_check)

    assert checked.status_code == 200, checked.text
    assert checked.json()["data"]["pinnedCommit"] == "commit-a"
    assert checked.json()["data"]["currentCommit"] == "commit-b"
    assert checked.json()["data"]["changed"] is True
    assert stale.status_code == 400 and stale.json()["data"]["reason"] == "concurrent_change"
    assert refused.status_code == 403
    assert raced.status_code == 400 and raced.json()["data"]["reason"] == "concurrent_change"
