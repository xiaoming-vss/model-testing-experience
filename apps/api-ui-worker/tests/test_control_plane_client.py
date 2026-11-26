from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from test_worker.contracts.parsing import (
    parse_case_run_snapshot,
    parse_snapshot_response,
    parse_suite_run_snapshot,
    parse_ui_task,
)
from test_worker.contracts.types import (
    UiCaseSnapshot,
    UiSuiteItemStartedPayload,
    UiTaskHeartbeatPayload,
    UiTaskStartedPayload,
    WorkerConfig,
)
from test_worker.control_plane.client import (
    ControlPlaneClient,
    ControlPlaneRequestError,
)
from test_worker.ui.step_normalizer import normalize_case_steps


class FakeHttpClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def request(
        self, method: str, pathname: str, json: dict | None = None
    ) -> httpx.Response:
        return self.response

    def post(self, pathname: str, json: dict | None = None) -> httpx.Response:
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
        trace_enabled=True,
        snapshot_file="",
    )


def test_claim_api_task_unwraps_standard_success_envelope() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request(
        "POST", "http://control-plane/internal/api-worker/tasks/claim"
    )
    client._client = FakeHttpClient(
        httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "data": {
                    "taskId": "task-1",
                    "taskType": "api_case_debug",
                    "runId": "run-1",
                    "caseId": "case-1",
                    "leaseSeconds": 60,
                },
            },
            request=request,
        )
    )

    task = client.claim_api_task()

    assert task is not None
    assert task["taskId"] == "task-1"
    assert task["taskType"] == "api_case_debug"


def test_parse_ui_task_ignores_unknown_claim_fields() -> None:
    task = parse_ui_task(
        {
            "taskId": "task-1",
            "taskType": "suite_run",
            "runId": "run-1",
            "leaseSeconds": 60,
            "futureClaimField": True,
        }
    )

    assert task.task_id == "task-1"
    assert task.task_type == "suite_run"
    assert task.lease_seconds == 60
    assert not hasattr(task, "futureClaimField")


def test_parse_ui_case_run_snapshot_keeps_screenshot_policy() -> None:
    snapshot = parse_case_run_snapshot(
        {
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
        }
    )

    assert snapshot is not None
    assert snapshot.suite is not None
    assert snapshot.suite.screenshot_policy == "after_each_step"
    assert snapshot.case.steps_json == []


def test_parse_ui_suite_run_snapshot_defaults_screenshot_policy() -> None:
    snapshot = parse_suite_run_snapshot(
        {
            "taskId": "task-1",
            "runId": "run-1",
            "suite": {
                "suiteId": "suite-1",
                "name": "Login Suite",
            },
            "items": [],
        },
        default_screenshot_policy="on_failure",
    )

    assert snapshot is not None
    assert snapshot.suite is not None
    assert snapshot.suite.screenshot_policy == "on_failure"


def test_snapshot_parser_ignores_unknown_control_plane_fields() -> None:
    snapshot = parse_snapshot_response(
        {
            "taskType": "case_debug",
            "futureTopLevel": True,
            "caseRun": {
                "taskId": "task-1",
                "runId": "run-1",
                "futureRunField": "ignored",
                "case": {
                    "caseId": "case-1",
                    "name": "Login",
                    "steps": [
                        {
                            "keyword": "click",
                            "futureStepField": "ignored",
                        }
                    ],
                    "futureCaseField": "ignored",
                },
            },
        },
        default_task_id="task-fallback",
    )

    assert snapshot.case_run is not None
    assert snapshot.case_run.task_id == "task-1"
    assert snapshot.case_run.case.steps is not None
    assert snapshot.case_run.case.steps[0].keyword == "click"
    assert not hasattr(snapshot.case_run.case.steps[0], "futureStepField")
    assert not hasattr(snapshot.case_run.case, "futureCaseField")
    assert not hasattr(snapshot.case_run, "futureRunField")


def test_explicit_steps_and_steps_json_read_a_step_the_same_way() -> None:
    step = {
        "keyword": "input",
        "orderNo": 2,
        "locatorType": "css",
        "saveTo": [{"name": "token", "source": "value"}],
    }

    from_steps = parse_case_run_snapshot(
        {"case": {"caseId": "c", "name": "n", "steps": [step]}}
    )
    from_json = normalize_case_steps(
        UiCaseSnapshot(case_id="c", name="n", steps_json=[step])
    )

    # The explicit path used to drop saveTo, so its extractions silently never ran.
    assert from_steps is not None and from_steps.case.steps == from_json
    assert from_json[0].save_to == [{"name": "token", "source": "value"}]


@pytest.mark.parametrize("save_to", ["token", [{"name": "token"}, "x"]])
def test_a_step_whose_save_to_is_not_an_object_array_is_refused(save_to) -> None:
    step = {"keyword": "input", "saveTo": save_to}

    with pytest.raises(ValueError, match="步骤 1 的 saveTo 必须是对象数组"):
        parse_case_run_snapshot({"case": {"caseId": "c", "name": "n", "steps": [step]}})
    with pytest.raises(ValueError, match="步骤 1 的 saveTo 必须是对象数组"):
        normalize_case_steps(UiCaseSnapshot(case_id="c", name="n", steps_json=[step]))


def test_serialization_keeps_local_path_until_artifact_publication(tmp_path) -> None:
    config = replace(
        _config(),
        artifacts_root_dir=str(tmp_path),
    )
    client = ControlPlaneClient(config)

    result = client._to_camel_case(
        {
            "step_results": [
                {
                    "screenshot_path": str(tmp_path / "run 1" / "step 1.png"),
                }
            ],
        }
    )

    assert result["stepResults"][0]["screenshotPath"] == str(
        tmp_path / "run 1" / "step 1.png"
    )


def test_ui_case_snapshot_parses_suite_browser_settings() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request(
        "GET", "http://control-plane/internal/ui-worker/tasks/task-1/snapshot"
    )
    client._client = FakeHttpClient(
        httpx.Response(
            200,
            json={
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
            },
            request=request,
        )
    )

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
    request = httpx.Request(
        "GET", "http://control-plane/internal/ui-worker/tasks/task-1/snapshot"
    )
    client._client = FakeHttpClient(
        httpx.Response(
            200,
            json={
                "taskType": "suite_run",
                "suiteRun": {
                    "suiteRunId": "suite-run-1",
                    "suite": {
                        "suiteId": "suite-1",
                        "name": "suite",
                    },
                    "items": [
                        {
                            "itemId": "item-1",
                            "continueOnFailure": False,
                            "case": {
                                "caseId": "case-1",
                                "name": "case",
                                "steps": [],
                            },
                        }
                    ],
                },
            },
            request=request,
        )
    )

    snapshot = client.get_task_snapshot("task-1")

    assert snapshot.suite_run is not None
    assert snapshot.suite_run.task_id == "task-1"
    assert snapshot.suite_run.run_id == "suite-run-1"


def test_request_error_keeps_route_and_status_without_response_body() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request(
        "GET", "http://control-plane/internal/ui-worker/tasks/task-1/snapshot"
    )
    client._client = FakeHttpClient(
        httpx.Response(
            500,
            text='{"code":"INTERNAL_ERROR","message":"SECRET-MARKER response body"}',
            request=request,
        )
    )

    with pytest.raises(ControlPlaneRequestError) as caught:
        client._request("GET", "/internal/ui-worker/tasks/task-1/snapshot")

    message = str(caught.value)
    assert "GET" in message
    assert "/internal/ui-worker/tasks/task-1/snapshot" in message
    assert "500" in message
    assert "server error" in message
    assert "code=INTERNAL_ERROR" in message
    assert "SECRET-MARKER" not in message


def test_request_error_without_json_code_uses_generic_status_text() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request(
        "PATCH", "http://control-plane/internal/ui-worker/tasks/task-1"
    )
    client._client = FakeHttpClient(
        httpx.Response(400, text="SECRET-MARKER raw body", request=request)
    )

    with pytest.raises(ControlPlaneRequestError) as caught:
        client._request("PATCH", "/internal/ui-worker/tasks/task-1?token=SECRET-MARKER")

    message = str(caught.value)
    assert "PATCH /internal/ui-worker/tasks/task-1 -> 400 bad request" in message
    assert "SECRET-MARKER" not in message
    assert "code=" not in message


def test_claim_next_task_error_uses_safe_message() -> None:
    client = ControlPlaneClient(_config())
    request = httpx.Request(
        "POST", "http://control-plane/internal/api-worker/tasks/claim-next"
    )
    client._client = FakeHttpClient(
        httpx.Response(503, text="SECRET-MARKER unavailable", request=request)
    )

    with pytest.raises(ControlPlaneRequestError) as caught:
        client.claim_next_task()

    message = str(caught.value)
    assert "POST /internal/api-worker/tasks/claim-next -> 503 server error" in message
    assert "SECRET-MARKER" not in message


def test_control_plane_error_constructor_drops_unsafe_error_codes() -> None:
    error = ControlPlaneRequestError(
        "GET", "/task?token=SECRET-MARKER", 403, "BAD CODE"
    )

    assert error.status_code == 403
    assert error.pathname == "/task"
    assert error.error_code == ""
    assert "SECRET-MARKER" not in str(error)
    assert "BAD CODE" not in str(error)


class RecordingHttpClient(FakeHttpClient):
    """Keeps every request body so a test can read the keys that go over the wire."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(response)
        self.bodies: list[dict | None] = []

    def request(
        self, method: str, pathname: str, json: dict | None = None
    ) -> httpx.Response:
        self.bodies.append(json)
        return self.response


def test_ui_lifecycle_payloads_use_camel_case_keys_like_every_other_payload() -> None:
    client = ControlPlaneClient(_config())
    http = RecordingHttpClient(
        httpx.Response(204, request=httpx.Request("POST", "http://control-plane/x"))
    )
    client._client = http

    client.report_task_started(
        "task-1", UiTaskStartedPayload(worker_id="worker-a", started_at="t0")
    )
    client.report_task_heartbeat(
        "task-1", UiTaskHeartbeatPayload(worker_id="worker-a", heartbeat_at="t1")
    )
    client.report_suite_item_started(
        "task-1",
        "item-1",
        UiSuiteItemStartedPayload(run_id="run-1", case_id="case-1", started_at="t2"),
    )

    assert http.bodies == [
        {"workerId": "worker-a", "startedAt": "t0"},
        {"workerId": "worker-a", "heartbeatAt": "t1"},
        {
            "workerId": "worker-a",
            "runId": "run-1",
            "caseId": "case-1",
            "startedAt": "t2",
        },
    ]


def test_transport_failure_is_a_control_plane_error_without_the_exception_text() -> (
    None
):
    class DisconnectingHttpClient:
        def request(
            self, method: str, pathname: str, json: dict | None = None
        ) -> httpx.Response:
            raise httpx.ConnectError(
                "SECRET-MARKER https://user:pass@control-plane/internal",
                request=httpx.Request("GET", "http://control-plane/internal"),
            )

    client = ControlPlaneClient(_config())
    client._client = DisconnectingHttpClient()

    with pytest.raises(ControlPlaneRequestError) as caught:
        client._request("GET", "/internal/ui-worker/tasks/task-1/snapshot")

    assert caught.value.status_code == 0
    assert str(caught.value) == (
        "control plane request failed: GET /internal/ui-worker/tasks/task-1/snapshot"
        " -> 0 no response"
    )


@pytest.mark.parametrize("status, expected", [(204, None), (404, NotImplemented)])
def test_claim_next_task_reports_an_empty_queue_and_an_older_server(
    status, expected
) -> None:
    client = ControlPlaneClient(_config())
    client._client = FakeHttpClient(
        httpx.Response(
            status, request=httpx.Request("POST", "http://control-plane/claim-next")
        )
    )

    assert client.claim_next_task() is expected


def test_claim_next_task_returns_the_unwrapped_task() -> None:
    client = ControlPlaneClient(_config())
    client._client = FakeHttpClient(
        httpx.Response(
            200,
            json={"code": 0, "data": {"taskId": "task-1", "domain": "ui"}},
            request=httpx.Request("POST", "http://control-plane/claim-next"),
        )
    )

    assert client.claim_next_task() == {"taskId": "task-1", "domain": "ui"}
