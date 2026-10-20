from dataclasses import replace

import pytest
from integration_test_driver import dispatch_sync, enable
from support.project_api import api as api
from test_bug_zentao_push_api import setup as setup

from testing_agent.core.config import get_settings


def test_migrated_fixture_runs_public_queue_and_worker_workflow(api, setup):
    response = dispatch_sync(api, setup)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["latestJob"]["jobStatus"] == "succeeded"
    assert len(setup["remote"].writes) == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_removed_writes_never_call_remote_even_when_worker_disabled(api, setup, enabled):
    current = enable(api)
    settings = replace(
        current, integration_execution=replace(current.integration_execution, enabled=enabled)
    )
    api.app.dependency_overrides[get_settings] = lambda: settings
    before = list(setup["remote"].calls)
    for method in ("POST", "PATCH"):
        response = api.request(method, setup["url"], headers=setup["owner"], json={})
        assert response.status_code == 405, response.text
        assert response.headers["allow"] == "GET"
    operations = api.get("/openapi.json").json()["paths"]["/v1/bugs/{bugId}/zentao-push"]
    assert "post" not in operations and "patch" not in operations
    assert setup["remote"].calls == before
