import logging
import time
from typing import Any

import pytest

from testing_agent_integration_worker.core.errors import PreflightError
from testing_agent_integration_worker.domain.bug_description import DescriptionError
from testing_agent_integration_worker.domain.execution import Execution, ExecutionWindow
from testing_agent_integration_worker.gateways.mcp import McpCallError
from testing_agent_integration_worker.repositories.evidence import EvidenceRepository
from testing_agent_integration_worker.schemas.job import Access, ClaimJob, JobInput
from testing_agent_integration_worker.schemas.step import Operation, Permit
from testing_agent_integration_worker.services.step_execution import StepExecution

TARGET = {"instanceUrl": "http://zentao.fixture/sub", "mcpServiceId": "service-1"}


class ControlPlane:
    def __init__(self, permit: Permit) -> None:
        self.permit = permit
        self.events: list[Any] = []

    async def prepare(self, job_id: str, step_key: str, body: dict[str, Any]) -> Permit:
        return self.permit

    async def result(self, job_id: str, step_key: str, event, *, evidence: bool = False):
        self.events.append(event)
        return {"jobStatus": "running"}


class Gateway:
    def __init__(self, *, connect_error: Exception | None = None, write=None) -> None:
        self.connect_error = connect_error
        self.write_result = write
        self.verified = 0

    async def __aenter__(self):
        if self.connect_error is not None:
            raise self.connect_error
        return self

    async def __aexit__(self, *_args):
        return None

    async def verify_instance(self, target):
        self.verified += 1

    async def write(self, operation):
        return self.write_result()


def _permit(*, write_allowed: bool = True, status: str = "write_intent") -> Permit:
    return Permit(
        operation_id="operation-1",
        status=status,
        write_allowed=write_allowed,
        permit_seconds=30,
        access=Access(endpoint="http://mcp.test", token="secret"),
        operation=Operation(tool="post_bugs", arguments={}, timeout_seconds=5),
    )


def _view() -> JobInput:
    return JobInput(
        job_id="job-1",
        job_status="running",
        task_type="zentao_bug_sync",
        protocol_version=1,
        result={},
        snapshot={"target": TARGET, "existingPayload": {}, "source": {"html": ""}},
        mapping={},
        input_revision="a" * 64,
        target_revision="b" * 64,
        steps=[],
    )


async def _run(permit: Permit, gateway: Gateway, tmp_path, *, write=None) -> tuple[Any, list]:
    control_plane = ControlPlane(permit)
    steps = StepExecution(
        control_plane, lambda _access: gateway, EvidenceRepository(tmp_path / "evidence.json")
    )
    claim = ClaimJob(
        jobId="job-1",
        jobStatus="running",
        taskType="zentao_bug_sync",
        protocolVersion=1,
        workerId="worker",
        claimGeneration=1,
        runtimeGeneration="epoch",
        leaseSeconds=60,
    )
    events: list[logging.LogRecord] = []
    logger = logging.getLogger("testing_agent_integration_worker.services.step_execution")
    handler = logging.Handler()
    handler.emit = events.append
    logger.addHandler(handler)
    try:
        await steps.execute(
            Execution(claim, ExecutionWindow(time.monotonic() + 60)),
            _view(),
            _step(),
            Access(endpoint="http://mcp.test", token="secret"),
            {},
        )
    finally:
        logger.removeHandler(handler)
    return control_plane.events[-1], events


def _step():
    from testing_agent_integration_worker.schemas.job import JobStep

    return JobStep(stepKey="create", kind="create_bug", status="pending", dependencies=[], input={})


async def test_mcp_failure_before_the_write_is_unavailable_not_rejected(tmp_path):
    event, _ = await _run(
        _permit(), Gateway(connect_error=McpCallError("MCP 请求超时或连接失败")), tmp_path
    )

    # Nothing reached Zentao, so the user is told the remote is unavailable, not that
    # Zentao refused an operation.
    assert event.status == "failed"
    assert event.result.error_code == "remote_unavailable"


async def test_rejected_write_stays_rejected(tmp_path):
    event, _ = await _run(
        _permit(),
        Gateway(write=lambda: (_ for _ in ()).throw(McpCallError("禅道返回业务失败结果"))),
        tmp_path,
    )

    assert event.status == "failed"
    assert event.result.error_code == "remote_rejected"


async def test_unexpected_error_is_classified_and_logged_without_its_message(tmp_path):
    def crash():
        raise RuntimeError("SECRET remote detail")

    event, records = await _run(_permit(), Gateway(write=crash), tmp_path)

    assert event.status == "unknown"
    assert event.result.error_code == "remote_uncertain"
    (record,) = [item for item in records if "unexpected error" in item.getMessage()]
    assert "error=RuntimeError" in record.getMessage()
    assert "SECRET" not in record.getMessage()
    assert "in crash" in record.getMessage()


@pytest.mark.parametrize(
    "status, code",
    [(409, "baseline_changed"), (400, "input_changed")],
)
def test_description_error_is_a_preflight_error_with_a_code(status, code):
    error = DescriptionError(status, "图片不属于原 Bug", status)

    assert isinstance(error, PreflightError)
    assert error.code == code
    assert error.http_status == status
