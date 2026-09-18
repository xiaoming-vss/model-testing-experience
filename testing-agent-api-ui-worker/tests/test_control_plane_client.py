from __future__ import annotations

from dataclasses import replace

import httpx

from test_worker.contracts.types import WorkerConfig
from test_worker.control_plane.client import ControlPlaneClient


class FakeHttpClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def request(self, method: str, pathname: str, json: dict | None = None) -> httpx.Response:
        return self.response


def _config() -> WorkerConfig:
    return WorkerConfig(
        mode="poll",
        worker_id="worker-a",
        control_plane_base_url="http://control-plane",
        worker_token="token",
        poll_interval_ms=3000,
        request_timeout_ms=15000,
        heartbeat_interval_ms=10000,
        artifacts_root_dir="./artifacts",
        default_headless=True,
        default_slow_mo_ms=0,
        trace_enabled=True,
        screenshot_on_failure=True,
        snapshot_file="",
    )


def test_claim_api_task_unwraps_standard_success_envelope() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request("POST", "http://control-plane/internal/api-worker/tasks/claim")
    client._client = FakeHttpClient(httpx.Response(200, json={
        "code": 0,
        "message": "success",
        "data": {
            "taskId": "task-1",
            "taskType": "api_case_debug",
            "runId": "run-1",
            "caseId": "case-1",
            "leaseSeconds": 60,
        },
    }, request=request))

    task = client.claim_api_task()

    assert task is not None
    assert task["taskId"] == "task-1"
    assert task["taskType"] == "api_case_debug"


def test_parse_ui_case_run_snapshot_keeps_screenshot_policy() -> None:
    client = ControlPlaneClient(_config())

    snapshot = client._parse_case_run_snapshot({
        "taskId": "task-1",
        "runId": "run-1",
        "suite": {
            "suiteId": "suite-1",
            "name": "Login Suite",
            "screenshotPolicy": "after_each_step",
        },
        "case": {
            "caseId": "case-1",
            "suiteId": "suite-1",
            "name": "Login",
            "stepsJson": [],
        },
    })

    assert snapshot.suite is not None
    assert snapshot.suite.screenshot_policy == "after_each_step"
    assert snapshot.case.steps_json == []


def test_parse_ui_suite_run_snapshot_defaults_screenshot_policy() -> None:
    client = ControlPlaneClient(_config())

    snapshot = client._parse_suite_run_snapshot({
        "taskId": "task-1",
        "runId": "run-1",
        "suite": {
            "suiteId": "suite-1",
            "name": "Login Suite",
        },
        "items": [],
    })

    assert snapshot.suite is not None
    assert snapshot.suite.screenshot_policy == "on_failure"


def test_serialize_result_converts_screenshot_path_to_worker_url(tmp_path) -> None:
    config = replace(
        _config(),
        artifacts_root_dir=str(tmp_path),
        artifacts_base_url="http://worker-a:9010",
    )
    client = ControlPlaneClient(config)

    result = client._to_camel_case({
        "step_results": [{
            "screenshot_path": str(tmp_path / "run 1" / "step 1.png"),
        }],
    })

    assert result["stepResults"][0]["screenshotPath"] == (
        "http://worker-a:9010/run%201/step%201.png"
    )


def test_ui_case_snapshot_parses_suite_browser_settings() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request("GET", "http://control-plane/internal/ui-worker/tasks/task-1/snapshot")
    client._client = FakeHttpClient(httpx.Response(200, json={
        "taskType": "case_debug",
        "caseRun": {
            "taskId": "task-1",
            "runId": "run-1",
            "suite": {
                "suiteId": "suite-1",
                "name": "suite",
                "headless": False,
                "slowMoMs": 30,
                "viewportWidth": 1366,
                "viewportHeight": 768,
                "defaultStepTimeoutMs": 9000,
                "screenshotPolicy": "after_each_step",
            },
            "case": {
                "caseId": "case-1",
                "name": "case",
                "steps": [],
            },
        },
    }, request=request))

    snapshot = client.get_task_snapshot("task-1")

    assert snapshot.case_run is not None
    assert snapshot.case_run.suite is not None
    assert snapshot.case_run.suite.headless is False
    assert snapshot.case_run.suite.slow_mo_ms == 30
    assert snapshot.case_run.suite.viewport_width == 1366
    assert snapshot.case_run.suite.viewport_height == 768
    assert snapshot.case_run.suite.default_step_timeout_ms == 9000
    assert snapshot.case_run.suite.screenshot_policy == "after_each_step"


def test_ui_suite_snapshot_uses_outer_task_id_and_suite_run_id() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request("GET", "http://control-plane/internal/ui-worker/tasks/task-1/snapshot")
    client._client = FakeHttpClient(httpx.Response(200, json={
        "taskType": "suite_run",
        "suiteRun": {
            "suiteRunId": "suite-run-1",
            "suite": {
                "suiteId": "suite-1",
                "name": "suite",
            },
            "items": [{
                "itemId": "item-1",
                "continueOnFailure": False,
                "case": {
                    "caseId": "case-1",
                    "name": "case",
                    "steps": [],
                },
            }],
        },
    }, request=request))

    snapshot = client.get_task_snapshot("task-1")

    assert snapshot.suite_run is not None
    assert snapshot.suite_run.task_id == "task-1"
    assert snapshot.suite_run.run_id == "suite-run-1"
