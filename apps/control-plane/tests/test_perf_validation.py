import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.core.config import get_settings
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.worker_task import WorkerTaskService

_YAML = """
specVersion: "1.0"
case:
  name: ping
  steps:
    - name: ping
      method: GET
      path: /ping
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""

_SECRET_YAML = """
specVersion: "1.0"
case:
  name: secret
  steps:
    - name: ping
      method: GET
      path: /ping
      headers:
        Authorization: "Bearer {{env.api_token}}"
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""


def _settings(api):
    settings = replace(
        get_settings(),
        integration_key="test-integration-key",
        perf_worker_key="perf-worker-token",
    )
    api.app.dependency_overrides[get_settings] = lambda: settings
    return settings


def _env(api, headers, project_id, *, kind="perf"):
    response = api.post(
        f"/v1/projects/{project_id}/api-environments",
        headers=headers,
        json={
            "name": f"{kind}-env",
            "kind": kind,
            "baseUrl": "http://127.0.0.1:18080",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["environmentId"]


def _connection(api, headers, project_id, name="prom"):
    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={
            "name": name,
            "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]


def _case(api, headers, project_id, yaml_text=_YAML):
    return api.post(
        f"/v1/projects/{project_id}/perf-cases",
        headers=headers,
        json={"name": f"case-{datetime.now(UTC).timestamp()}", "yaml": yaml_text},
    )


def test_perf_case_update_increments_version_and_name_is_unique(api):
    _settings(api)
    _, headers = account(api, "case-version-owner")
    project_id = project(api, headers, "case-version-project")
    created = _case(api, headers, project_id)
    assert created.status_code == 200, created.text
    case = created.json()["data"]
    assert case["version"] == 1

    updated = api.patch(
        f"/v1/perf-cases/{case['caseId']}",
        headers=headers,
        json={"yaml": _YAML + "\n# version bump\n"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["version"] == 2

    duplicate = api.post(
        f"/v1/projects/{project_id}/perf-cases",
        headers=headers,
        json={"name": case["name"], "yaml": _YAML},
    )
    assert duplicate.status_code == 409, duplicate.text


def test_monitoring_connection_write_secrets_are_masked_and_update_keeps_them(api):
    _settings(api)
    _, headers = account(api, "monitor-owner")
    project_id = project(api, headers, "monitor-project")

    created = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={
            "name": "prom",
            "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
            "remoteWriteAuth": {
                "type": "basic",
                "username": "writer",
                "password": "write-secret",
            },
        },
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["hasRemoteWriteCredentials"] is True
    assert "write-secret" not in created.text

    updated = api.patch(
        f"/v1/monitoring-connections/{data['connectionId']}",
        headers=headers,
        json={"name": "prom-renamed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["hasRemoteWriteCredentials"] is True

    cleared = api.patch(
        f"/v1/monitoring-connections/{data['connectionId']}",
        headers=headers,
        json={"remoteWriteAuth": {"type": "none"}},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["hasRemoteWriteCredentials"] is False


def test_monitoring_connection_url_rejects_embedded_credentials(api):
    _settings(api)
    _, headers = account(api, "monitor-url-owner")
    project_id = project(api, headers, "monitor-url-project")

    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={
            "name": "bad",
            "remoteWriteUrl": "http://user:pass@127.0.0.1:19090/api/v1/write",
        },
    )
    assert response.status_code == 400, response.text


def test_monitoring_connection_rejects_removed_query_and_grafana_fields(api):
    _settings(api)
    _, headers = account(api, "monitor-removed-owner")
    project_id = project(api, headers, "monitor-removed-project")

    for extra in (
        {"queryUrl": "http://127.0.0.1:19090"},
        {"grafanaUrl": "https://grafana.example.com"},
        {"grafanaDashboardUid": "perf-overview"},
        {"defaultFilters": {"namespace": "perf"}},
    ):
        response = api.post(
            f"/v1/projects/{project_id}/monitoring-connections",
            headers=headers,
            json={
                "name": f"removed-{next(iter(extra))}",
                "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
                **extra,
            },
        )
        assert response.status_code == 400, response.text


def test_viewer_cannot_manage_monitoring_connections(api):
    _settings(api)
    _, owner = account(api, "monitor-perm-owner")
    viewer_user, viewer = account(api, "monitor-perm-viewer")
    project_id = project(api, owner, "monitor-perm-project")
    added = api.post(
        f"/v1/projects/{project_id}/members",
        headers=owner,
        json={"name": viewer_user["name"], "role": "viewer"},
    )
    assert added.status_code == 200, added.text

    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=viewer,
        json={
            "name": "prom",
            "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write",
        },
    )
    assert response.status_code == 403, response.text


def test_perf_case_rejects_duplicate_yaml_keys_and_platform_fields(api):
    _settings(api)
    _, headers = account(api, "yaml-owner")
    project_id = project(api, headers, "yaml-project")

    duplicate = _YAML.replace('specVersion: "1.0"', 'specVersion: "1.0"\nspecVersion: "1.0"')
    response = _case(api, headers, project_id, duplicate)
    assert response.status_code == 400, response.text
    assert "重复键" in response.text

    with_platform = _YAML + "\nenvironment:\n  baseUrl: http://x\n"
    response = _case(api, headers, project_id, with_platform)
    assert response.status_code == 400, response.text
    assert "environment" in response.text


def test_perf_case_accepts_staged_vus_load(api):
    _settings(api)
    _, headers = account(api, "staged-owner")
    project_id = project(api, headers, "staged-project")
    yaml_text = _YAML.replace(
        '  load:\n    model: vus\n    vus: 1\n    duration: "1s"',
        "  load:\n"
        "    model: staged_vus\n"
        "    profile: spike\n"
        "    stages:\n"
        '      - target: 5\n        ramp: "0s"\n        hold: "30s"\n'
        '      - target: 50\n        ramp: "5s"\n        hold: "10s"\n'
        '      - target: 5\n        ramp: "5s"\n        hold: "30s"\n'
        '    finalDown: "0s"',
    )

    response = _case(api, headers, project_id, yaml_text)

    assert response.status_code == 200, response.text


def test_perf_case_rejects_staged_vus_with_invalid_stages(api):
    _settings(api)
    _, headers = account(api, "staged-invalid-owner")
    project_id = project(api, headers, "staged-invalid-project")

    empty_stages = _YAML.replace(
        '  load:\n    model: vus\n    vus: 1\n    duration: "1s"',
        "  load:\n    model: staged_vus\n    stages: []",
    )
    response = _case(api, headers, project_id, empty_stages)
    assert response.status_code == 400, response.text
    assert "stages" in response.text

    invalid_profile = _YAML.replace(
        '  load:\n    model: vus\n    vus: 1\n    duration: "1s"',
        "  load:\n"
        "    model: staged_vus\n"
        "    profile: ramp\n"
        "    stages:\n"
        '      - target: 5\n        ramp: "0s"\n        hold: "30s"',
    )
    response = _case(api, headers, project_id, invalid_profile)
    assert response.status_code == 400, response.text
    assert "profile" in response.text


def test_perf_case_data_source_requires_attached_file(api):
    _settings(api)
    _, headers = account(api, "data-owner")
    project_id = project(api, headers, "data-project")
    yaml_text = _YAML.replace(
        "  acceptance:",
        "  data:\n"
        "    - name: users\n"
        "      source: users.csv\n"
        "      strategy: cycle\n\n"
        "  acceptance:",
    )
    response = _case(api, headers, project_id, yaml_text)
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 3908


def test_perf_run_rejects_non_perf_environment(api):
    _settings(api)
    _, headers = account(api, "env-kind-owner")
    project_id = project(api, headers, "env-kind-project")
    environment_id = _env(api, headers, project_id, kind="api")
    connection_id = _connection(api, headers, project_id)
    case = _case(api, headers, project_id)
    assert case.status_code == 200, case.text

    response = api.post(
        f"/v1/perf-cases/{case.json()['data']['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 3905


def test_secret_environment_value_is_redacted_in_public_spec(api):
    settings = _settings(api)
    _, headers = account(api, "secret-owner")
    project_id = project(api, headers, "secret-project")
    environment_id = _env(api, headers, project_id)
    added = api.post(
        f"/v1/api-environments/{environment_id}/vars",
        headers=headers,
        json={"varKey": "api_token", "value": "top-secret", "isSecret": True},
    )
    assert added.status_code == 200, added.text
    connection_id = _connection(api, headers, project_id)
    case = _case(api, headers, project_id, _SECRET_YAML)
    assert case.status_code == 200, case.text

    response = api.post(
        f"/v1/perf-cases/{case.json()['data']['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["data"]["runId"]

    async def stored_specs():
        async with api.app.state.test_sessions() as session:
            run = await session.scalar(select(PerfRun).where(PerfRun.run_id == run_id))
            assert run is not None
            cipher = IntegrationCredentialCipher(settings.integration_key)
            private = json.loads(cipher.decrypt(run.private_payload))
            return run.spec_json, private["spec"]

    public_spec, private_spec = asyncio.run(stored_specs())
    assert public_spec["environment"]["variables"]["api_token"] == "********"
    assert "top-secret" not in json.dumps(public_spec)
    assert private_spec["environment"]["variables"]["api_token"] == "top-secret"


def test_lease_expiry_marks_perf_run_failed(api):
    _settings(api)
    _, headers = account(api, "lease-owner")
    project_id = project(api, headers, "lease-project")
    environment_id = _env(api, headers, project_id)
    connection_id = _connection(api, headers, project_id)
    case = _case(api, headers, project_id)
    run = api.post(
        f"/v1/perf-cases/{case.json()['data']['caseId']}/runs",
        headers=headers,
        json={
            "environmentId": environment_id,
            "monitoringConnectionId": connection_id,
        },
    ).json()["data"]
    run_id = run["runId"]
    claim = api.post(
        "/internal/perf-worker/tasks/claim",
        headers={"X-Worker-Token": "perf-worker-token"},
        json={"workerId": "lease-worker"},
    )
    assert claim.status_code == 200, claim.text

    async def expire():
        async with api.app.state.test_sessions() as session:
            task = await session.scalar(
                select(WorkerTask).where(WorkerTask.domain == "perf", WorkerTask.run_id == run_id)
            )
            assert task is not None
            task.lease_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            await session.commit()
            processed = await WorkerTaskService(WorkerTaskRepository(session)).expire_leases("perf")
            await session.commit()
            refreshed = await session.scalar(select(PerfRun).where(PerfRun.run_id == run_id))
            return processed, refreshed

    processed, refreshed = asyncio.run(expire())
    assert processed == 1
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.outcome == "execution_error"
