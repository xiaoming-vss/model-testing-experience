"""Shared performance API preparation; no collected cases."""

from dataclasses import replace

from testing_agent.core.config import get_settings

# A confirmed ping case with a one-second, single-virtual-user load.
PERF_YAML = """
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

WORKER_KEY = "perf-worker-token"


def worker_headers():
    """Headers a performance worker sends; the token is the one worker_settings installs."""
    return {"X-Worker-Token": WORKER_KEY}


def worker_settings(api):
    """Replace the integration and perf worker keys, override get_settings and return them."""
    settings = replace(
        get_settings(),
        integration_key="test-integration-key",
        perf_worker_key=WORKER_KEY,
    )
    api.app.dependency_overrides[get_settings] = lambda: settings
    return settings


def environment(api, headers, project_id, name="perf-env", kind="perf"):
    """Create an API environment and return its id."""
    response = api.post(
        f"/v1/projects/{project_id}/api-environments",
        headers=headers,
        json={"name": name, "kind": kind, "baseUrl": "http://127.0.0.1:18080"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["environmentId"]


def monitoring_connection(api, headers, project_id, name="prom"):
    """Create a monitoring connection without remote-write credentials and return its id."""
    response = api.post(
        f"/v1/projects/{project_id}/monitoring-connections",
        headers=headers,
        json={"name": name, "remoteWriteUrl": "http://127.0.0.1:19090/api/v1/write"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]
