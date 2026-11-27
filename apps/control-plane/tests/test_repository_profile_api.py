"""Repository profile HTTP lifecycle through the auxiliary execution pipeline."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from support.project_api import account, project, requirement, seed_llm_connection
from support.project_api import api as api
from support.requirement_versions import adopt_material

from testing_agent.api.deps import verify_worker_token
from testing_agent.services.repository_profile import RepositoryProfileService
from testing_agent.services.requirement_material_source import material_reference_fields

PROFILE_JSON = json.dumps(
    {
        "repositories": [
            {
                "repositoryId": "repo-1",
                "pathWithNamespace": "team/repo-1",
                "role": "backend",
                "responsibilitySummary": "提供登录接口",
                "techStack": ["Java", "Spring Boot"],
                "keyPaths": ["src/main/java"],
                "confidence": 0.86,
                "evidence": ["pom.xml"],
            }
        ],
        "overallSummary": "当前需求主要涉及后端仓库",
    },
    ensure_ascii=False,
)


@pytest.fixture
def profile_project(api, monkeypatch):
    """Owner and viewer of a project whose requirement has adopted material and a model."""

    _, owner = account(api, "profile-owner")
    _, viewer = account(api, "profile-viewer")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "profile-viewer", "role": "viewer"},
        ).status_code
        == 200
    )
    requirement_id = requirement(api, owner, pid)
    material_id = adopt_material(api, requirement_id, headers=owner)
    connection_id = seed_llm_connection(
        api,
        owner,
        project_id=pid,
        base_url="https://llm.example/v1",
        api_key="secret",
    )

    async def profile_snapshot(
        task, run_id, worker_task_id, instruction, *, user_id, connection_ids, **kwargs
    ):
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "taskType": "repository_profile",
            "requirementId": requirement_id,
            "requirement": {"name": "需求", "documentContent": kwargs["current_material"].content},
            **material_reference_fields(kwargs["current_material"]),
            "bindings": [
                {
                    "bindingId": "binding-1",
                    "repositoryId": "repo-1",
                    "instanceUrl": "https://gitlab.example.com",
                    "pathWithNamespace": "team/repo-1",
                    "branch": "main",
                    "cloneUrl": "",
                    "headCommit": "",
                    "connectionId": "",
                    "profileError": "未找到该仓库可用的 GitLab 个人授权",
                }
            ],
        }

    # The profile worker is authorized by the overridden token check, not by a real worker.
    build_snapshot = AsyncMock(side_effect=profile_snapshot)
    monkeypatch.setattr(RepositoryProfileService, "build_snapshot", build_snapshot)
    monkeypatch.setitem(api.app.dependency_overrides, verify_worker_token, lambda: None)
    yield SimpleNamespace(
        api=api,
        owner=owner,
        viewer=viewer,
        pid=pid,
        requirement_id=requirement_id,
        material_id=material_id,
        connection_id=connection_id,
        build_snapshot=build_snapshot,
    )


def create_task(context):
    """Create the repository-profile task of the project's requirement; returns its data."""
    response = context.api.post(
        f"/v1/projects/{context.pid}/repository-profile-tasks",
        headers=context.owner,
        json={"requirementId": context.requirement_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def run_request(context, task_id, headers, request_id=None):
    """Ask to run the task; the raw response lets callers assert refusals."""
    body = {"connectionId": context.connection_id}
    if request_id is not None:
        body["requestId"] = request_id
    return context.api.post(
        f"/v1/repository-profile-tasks/{task_id}/run", headers=headers, json=body
    )


def start_run(context, task_id, request_id="profile-request"):
    """Run the task as the owner; returns the run data."""
    response = run_request(context, task_id, context.owner, request_id)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def claim_run(api, worker_id):
    """Let a worker claim the pending run; returns the queue task and attempt ids."""
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": worker_id})
    assert claim.status_code == 200, claim.text
    return claim.json()["taskId"], claim.json()["attemptId"]


def report_start(api, worker_id, queue_id, attempt_id):
    return api.post(
        f"/internal/ai-worker/tasks/{queue_id}/started",
        json={"workerId": worker_id, "attemptId": attempt_id},
    )


def report_progress(api, worker_id, queue_id, attempt_id):
    return api.patch(
        f"/internal/ai-worker/tasks/{queue_id}/progress",
        json={
            "workerId": worker_id,
            "attemptId": attempt_id,
            "currentStage": "profiling",
            "stageStatus": "running",
        },
    )


def report_completion(api, worker_id, queue_id, attempt_id, **result):
    return api.post(
        f"/internal/ai-worker/tasks/{queue_id}/completed",
        json={"workerId": worker_id, "attemptId": attempt_id, **result},
    )


def succeed_run(context, task_id):
    """Run the task and report profiling progress and a successful result."""
    run = start_run(context, task_id)
    queue_id, attempt_id = claim_run(context.api, "profile-worker")
    assert report_start(context.api, "profile-worker", queue_id, attempt_id).status_code == 204
    assert report_progress(context.api, "profile-worker", queue_id, attempt_id).status_code == 204
    assert (
        report_completion(
            context.api,
            "profile-worker",
            queue_id,
            attempt_id,
            status="success",
            resultYaml=PROFILE_JSON,
        ).status_code
        == 204
    )
    return run, attempt_id


def fail_run(context, task_id):
    """Run the finished task again and report a failure without a result."""
    start_run(context, task_id, "profile-request-failed")
    queue_id, attempt_id = claim_run(context.api, "profile-worker-failed")
    assert (
        report_start(context.api, "profile-worker-failed", queue_id, attempt_id).status_code == 204
    )
    assert (
        report_completion(
            context.api,
            "profile-worker-failed",
            queue_id,
            attempt_id,
            status="failed",
            errorMessage="profile failed",
        ).status_code
        == 204
    )


def candidates_url(context):
    return f"/v1/requirements/{context.requirement_id}/repository-profile/candidates"


def test_repository_profile_task_is_created_for_the_requirement(profile_project):
    task = create_task(profile_project)

    assert task["taskType"] == "repository_profile"


def test_run_is_built_from_the_adopted_material_and_starts_pending(profile_project):
    task_id = create_task(profile_project)["taskId"]

    run = start_run(profile_project, task_id)

    material = profile_project.build_snapshot.await_args.kwargs["current_material"]
    assert material.candidate_id == profile_project.material_id
    assert run["status"] == "pending"


def test_second_run_is_refused_while_one_is_active(profile_project):
    task_id = create_task(profile_project)["taskId"]
    start_run(profile_project, task_id)

    active = run_request(profile_project, task_id, profile_project.owner, "profile-request-2")

    assert active.status_code == 400
    assert "仓库画像正在生成中" in active.text


def test_viewer_cannot_start_a_run(profile_project):
    task_id = create_task(profile_project)["taskId"]
    start_run(profile_project, task_id)

    refused = run_request(profile_project, task_id, profile_project.viewer)

    assert refused.status_code == 403


def test_worker_claims_the_run_by_request_id_without_gitlab_credentials(profile_project):
    task_id = create_task(profile_project)["taskId"]
    start_run(profile_project, task_id)

    queue_id, _ = claim_run(profile_project.api, "profile-worker")
    base = f"/internal/ai-worker/tasks/{queue_id}"
    payload = profile_project.api.get(f"{base}/snapshot").json()
    credentials = profile_project.api.get(f"{base}/gitlab-credentials")

    assert queue_id == "profile-request"
    assert payload["run"]["taskType"] == "repository_profile"
    assert credentials.status_code == 200, credentials.text
    assert credentials.json()["credentials"] == []


def test_worker_reports_start_progress_and_completion(profile_project):
    task_id = create_task(profile_project)["taskId"]
    start_run(profile_project, task_id)
    queue_id, attempt_id = claim_run(profile_project.api, "profile-worker")

    started = report_start(profile_project.api, "profile-worker", queue_id, attempt_id)
    progress = report_progress(profile_project.api, "profile-worker", queue_id, attempt_id)
    completed = report_completion(
        profile_project.api,
        "profile-worker",
        queue_id,
        attempt_id,
        status="success",
        resultYaml=PROFILE_JSON,
    )

    assert started.status_code == 204, started.text
    assert progress.status_code == 204, progress.text
    assert completed.status_code == 204, completed.text


def test_completed_run_is_listed_as_not_requiring_review(profile_project):
    task_id = create_task(profile_project)["taskId"]
    run, _ = succeed_run(profile_project, task_id)

    history = profile_project.api.get(
        f"/v1/repository-profile-tasks/{task_id}/runs", headers=profile_project.owner
    )

    assert history.status_code == 200, history.text
    assert [item["runId"] for item in history.json()["data"]["items"]] == [run["runId"]]
    assert history.json()["data"]["items"][0]["reviewStatus"] == "not_required"


def test_completed_run_exposes_one_candidate_that_viewers_can_read(profile_project):
    task_id = create_task(profile_project)["taskId"]
    _, attempt_id = succeed_run(profile_project, task_id)
    url = candidates_url(profile_project)

    candidates = profile_project.api.get(url, headers=profile_project.owner)
    assert candidates.status_code == 200, candidates.text
    items = candidates.json()["data"]["items"]
    candidate = profile_project.api.get(
        url + f"/{items[0]['candidateId']}", headers=profile_project.owner
    )
    as_viewer = profile_project.api.get(url, headers=profile_project.viewer)

    assert len(items) == 1 and items[0]["currentAttemptId"] == attempt_id
    assert (
        json.loads(candidate.json()["data"]["content"])["overallSummary"]
        == "当前需求主要涉及后端仓库"
    )
    assert as_viewer.status_code == 200


def test_failed_run_keeps_the_completed_candidate(profile_project):
    task_id = create_task(profile_project)["taskId"]
    succeed_run(profile_project, task_id)
    url = candidates_url(profile_project)
    [completed] = profile_project.api.get(url, headers=profile_project.owner).json()["data"][
        "items"
    ]

    fail_run(profile_project, task_id)

    after_failure = profile_project.api.get(url, headers=profile_project.owner)
    assert after_failure.status_code == 200, after_failure.text
    assert [item["candidateId"] for item in after_failure.json()["data"]["items"]] == [
        completed["candidateId"]
    ]


def test_project_lists_the_profile_task(profile_project):
    task = create_task(profile_project)

    tasks = profile_project.api.get(
        f"/v1/projects/{profile_project.pid}/repository-profile-tasks",
        headers=profile_project.owner,
    )

    assert tasks.status_code == 200, tasks.text
    assert [item["taskId"] for item in tasks.json()["data"]["items"]] == [task["taskId"]]


def test_profile_runs_leave_the_code_risk_history_empty(profile_project):
    task_id = create_task(profile_project)["taskId"]
    succeed_run(profile_project, task_id)
    fail_run(profile_project, task_id)

    code_risk_latest = profile_project.api.get(
        f"/v1/projects/{profile_project.pid}/code-risk-analysis-tasks/latest-runs",
        headers=profile_project.owner,
    )

    assert code_risk_latest.status_code == 200, code_risk_latest.text
    assert code_risk_latest.json()["data"]["items"] == []


def test_profile_runs_add_no_generation_chain_stages(profile_project):
    task_id = create_task(profile_project)["taskId"]
    succeed_run(profile_project, task_id)
    fail_run(profile_project, task_id)

    chain = profile_project.api.get(
        f"/v1/requirements/{profile_project.requirement_id}/generation/requirement_analysis",
        headers=profile_project.owner,
    )

    assert chain.status_code == 200, chain.text
    assert [stage["stage"] for stage in chain.json()["data"]["stages"]] == [
        "requirement_review",
        "extracting_text",
        "historical_requirement_relations",
        "historical_test_case_verification",
    ]


def test_repository_profile_task_requires_requirement_and_write_access(api):
    _, owner = account(api, "profile-task-owner")
    _, viewer = account(api, "profile-task-viewer")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "profile-task-viewer", "role": "viewer"},
        ).status_code
        == 200
    )

    missing_requirement = api.post(
        f"/v1/projects/{pid}/repository-profile-tasks",
        headers=owner,
        json={},
    )
    assert missing_requirement.status_code == 400

    viewer_create = api.post(
        f"/v1/projects/{pid}/repository-profile-tasks",
        headers=viewer,
        json={"requirementId": "missing"},
    )
    assert viewer_create.status_code == 403
