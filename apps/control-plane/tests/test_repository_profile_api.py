"""Repository profile HTTP lifecycle through the auxiliary execution pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from support.project_api import account, project, requirement
from support.project_api import api as api

from testing_agent.api.deps import verify_worker_token
from testing_agent.services.repository_profile import RepositoryProfileService

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


def test_repository_profile_run_lifecycle_and_isolation(api, monkeypatch):
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
    from support.requirement_versions import approve_material

    material_id = approve_material(api, requirement_id)
    connection = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=owner,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example/v1",
            "apiKey": "secret",
            "modelId": "model",
        },
    )
    assert connection.status_code == 200, connection.text
    connection_id = connection.json()["data"]["connectionId"]

    task = api.post(
        f"/v1/projects/{pid}/repository-profile-tasks",
        headers=owner,
        json={"requirementId": requirement_id},
    )
    assert task.status_code == 200, task.text
    task_id = task.json()["data"]["taskId"]
    assert task.json()["data"]["taskType"] == "repository_profile"

    async def snapshot(
        task, run_id, worker_task_id, instruction, *, user_id, connection_ids, **kwargs
    ):
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "taskType": "repository_profile",
            "requirement": {"name": "需求"},
            "requirementMaterialVersion": {
                "versionId": material_id,
                "versionNo": 1,
                "taskId": "understanding-task",
                "runId": "understanding-run",
            },
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

    build_snapshot = AsyncMock(side_effect=snapshot)
    monkeypatch.setattr(RepositoryProfileService, "build_snapshot", build_snapshot)
    api.app.dependency_overrides[verify_worker_token] = lambda: None

    try:
        run = api.post(
            f"/v1/repository-profile-tasks/{task_id}/run",
            headers=owner,
            json={
                "connectionId": connection_id,
                "requestId": "profile-request",
                "requirementUnderstandingVersionId": material_id,
            },
        )
        assert run.status_code == 200, run.text
        assert build_snapshot.await_args.kwargs["material_version_id"] == material_id
        run_id = run.json()["data"]["runId"]
        assert run.json()["data"]["status"] == "pending"

        active = api.post(
            f"/v1/repository-profile-tasks/{task_id}/run",
            headers=owner,
            json={
                "connectionId": connection_id,
                "requestId": "profile-request-2",
                "requirementMaterialVersionId": material_id,
            },
        )
        assert active.status_code == 400
        assert "仓库画像正在生成中" in active.text

        assert (
            api.post(
                f"/v1/repository-profile-tasks/{task_id}/run",
                headers=viewer,
                json={"connectionId": connection_id},
            ).status_code
            == 403
        )

        claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "profile-worker"})
        assert claim.status_code == 200, claim.text
        queue_id, attempt_id = claim.json()["taskId"], claim.json()["attemptId"]
        assert queue_id == "profile-request"
        base = f"/internal/ai-worker/tasks/{queue_id}"
        snapshot_payload = api.get(f"{base}/snapshot").json()
        assert snapshot_payload["run"]["taskType"] == "repository_profile"
        credentials = api.get(f"{base}/gitlab-credentials")
        assert credentials.status_code == 200, credentials.text
        assert credentials.json()["credentials"] == []
        assert (
            api.post(
                f"{base}/started",
                json={"workerId": "profile-worker", "attemptId": attempt_id},
            ).status_code
            == 204
        )
        assert (
            api.patch(
                f"{base}/progress",
                json={
                    "workerId": "profile-worker",
                    "attemptId": attempt_id,
                    "currentStage": "profiling",
                    "stageStatus": "running",
                },
            ).status_code
            == 204
        )
        complete = api.post(
            f"{base}/completed",
            json={
                "workerId": "profile-worker",
                "attemptId": attempt_id,
                "status": "success",
                "resultYaml": PROFILE_JSON,
            },
        )
        assert complete.status_code == 204, complete.text

        detail = api.get(f"/v1/repository-profile-runs/{run_id}", headers=owner)
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["profile"]["overallSummary"] == "当前需求主要涉及后端仓库"
        assert detail.json()["data"]["profile"]["repositories"][0]["role"] == "backend"
        assert (
            detail.json()["data"]["snapshotJson"]["requirementMaterialVersion"]["versionId"]
            == material_id
        )
        assert api.get(f"/v1/repository-profile-runs/{run_id}", headers=viewer).status_code == 200

        history = api.get(f"/v1/repository-profile-tasks/{task_id}/runs", headers=owner)
        assert history.status_code == 200, history.text
        assert [item["runId"] for item in history.json()["data"]["items"]] == [run_id]
        assert history.json()["data"]["items"][0]["reviewStatus"] == "not_required"

        versions = api.get(f"/v1/repository-profile-tasks/{task_id}/versions", headers=owner)
        assert versions.status_code == 200, versions.text
        version_items = versions.json()["data"]["items"]
        assert len(version_items) == 1
        assert version_items[0]["versionNo"] == 1
        assert version_items[0]["label"] == "v1"
        assert version_items[0]["sourceRunId"] == run_id
        assert version_items[0]["profile"]["overallSummary"] == "当前需求主要涉及后端仓库"
        assert version_items[0]["requirementMaterialVersion"]["versionId"] == material_id
        assert (
            api.get(f"/v1/repository-profile-tasks/{task_id}/versions", headers=viewer).status_code
            == 200
        )

        failed_run = api.post(
            f"/v1/repository-profile-tasks/{task_id}/run",
            headers=owner,
            json={
                "connectionId": connection_id,
                "requestId": "profile-request-failed",
                "requirementMaterialVersionId": material_id,
            },
        )
        assert failed_run.status_code == 200, failed_run.text
        failed_claim = api.post(
            "/internal/ai-worker/tasks/claim", json={"workerId": "profile-worker-failed"}
        )
        assert failed_claim.status_code == 200, failed_claim.text
        failed_queue_id = failed_claim.json()["taskId"]
        failed_attempt_id = failed_claim.json()["attemptId"]
        failed_base = f"/internal/ai-worker/tasks/{failed_queue_id}"
        assert (
            api.post(
                f"{failed_base}/started",
                json={
                    "workerId": "profile-worker-failed",
                    "attemptId": failed_attempt_id,
                },
            ).status_code
            == 204
        )
        assert (
            api.post(
                f"{failed_base}/completed",
                json={
                    "workerId": "profile-worker-failed",
                    "attemptId": failed_attempt_id,
                    "status": "failed",
                    "errorMessage": "profile failed",
                },
            ).status_code
            == 204
        )
        versions_after_failure = api.get(
            f"/v1/repository-profile-tasks/{task_id}/versions", headers=owner
        )
        assert versions_after_failure.status_code == 200, versions_after_failure.text
        assert [item["versionId"] for item in versions_after_failure.json()["data"]["items"]] == [
            run_id
        ]

        tasks = api.get(f"/v1/projects/{pid}/repository-profile-tasks", headers=owner)
        assert tasks.status_code == 200, tasks.text
        assert [item["taskId"] for item in tasks.json()["data"]["items"]] == [task_id]

        code_risk_latest = api.get(
            f"/v1/projects/{pid}/code-risk-analysis-tasks/latest-runs", headers=owner
        )
        assert code_risk_latest.status_code == 200, code_risk_latest.text
        assert code_risk_latest.json()["data"]["items"] == []

        chain = api.get(
            f"/v1/requirements/{requirement_id}/generation/requirement_analysis",
            headers=owner,
        )
        assert chain.status_code == 200, chain.text
        assert all(
            stage["stage"] in {"extracting_text", "feature_understanding"}
            for stage in chain.json()["data"]["stages"]
        )
    finally:
        api.app.dependency_overrides.pop(verify_worker_token, None)


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
