from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest, RunUiSuiteRequest
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services.ui_test_case_run import UiTestCaseRunService
from testing_agent.services.worker import build_snapshot, complete_domain_run


class FakeUiRunRepository:
    session = AuthorizationDatabase()

    def __init__(self, cases):
        self.rows = []
        self.cases = cases
        self.suite = SimpleNamespace(
            suite_id="suite-1",
            requirement_id="requirement-1",
            name="xiaoming",
            headless=False,
            slow_mo_ms=300,
            viewport_width=1440,
            viewport_height=900,
            default_step_timeout_ms=5000,
            screenshot_policy="after_each_step",
        )
        self.requirement = SimpleNamespace(
            requirement_id="requirement-1",
            sprint_id="sprint-1",
        )
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.project = SimpleNamespace(project_id="project-1", user_id="user-1")

    async def get_case(self, case_id):
        return next((case for case in self.cases if case.case_id == case_id), None)

    async def get_suite(self, suite_id):
        return self.suite if suite_id == self.suite.suite_id else None

    async def get_requirement(self, requirement_id):
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == self.sprint.sprint_id else None

    async def get_project(self, project_id):
        return self.project if project_id == self.project.project_id else None

    async def list_cases(self, suite_id):
        return list(self.cases) if suite_id == self.suite.suite_id else []

    async def get_suite_run(self, suite_run_id):
        return getattr(self, "suite_run", None)

    async def list_suite_items(self, suite_run_id):
        return list(getattr(self, "suite_items", []))

    def add_all(self, rows):
        self.rows.extend(rows)

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, row):
        row.error_message = ""
        row.duration_ms = 0
        row.started_at = None
        row.finished_at = None
        row.created_at = None
        row.updated_at = None
        if isinstance(row, UiTestSuiteRun):
            row.success_count = 0
            row.failed_count = 0
            row.error_count = 0
            row.skipped_count = 0


def ui_case(case_id, name, order_no, steps):
    return SimpleNamespace(
        case_id=case_id,
        suite_id="suite-1",
        name=name,
        enabled=True,
        order_no=order_no,
        steps_json=steps,
    )


@pytest.mark.asyncio
async def test_debug_run_freezes_case_execution_data_in_snapshot():
    case = ui_case(
        "case-1",
        "登录成功",
        1,
        [{"orderNo": 1, "keyword": "open", "operationValue": "http://127.0.0.1:5173/"}],
    )
    repository = FakeUiRunRepository([case])

    await UiTestCaseRunService(repository).debug_run_case(
        "user-1", "case-1", DebugRunUiCaseRequest()
    )

    run = next(row for row in repository.rows if isinstance(row, UiTestCaseRun))
    assert run.snapshot_json["runId"] == run.run_id
    assert run.snapshot_json["suite"]["name"] == "xiaoming"
    assert run.snapshot_json["case"] == {
        "caseId": "case-1",
        "suiteId": "suite-1",
        "name": "登录成功",
        "enabled": True,
        "orderNo": 1,
        "stepsJson": [
            {
                "orderNo": 1,
                "keyword": "open",
                "operationValue": "http://127.0.0.1:5173/",
            }
        ],
    }


@pytest.mark.asyncio
async def test_suite_run_freezes_ordered_case_execution_data_and_item_ids():
    cases = [
        ui_case("case-1", "打开页面", 1, [{"orderNo": 1, "keyword": "open"}]),
        ui_case("case-2", "登录成功", 2, [{"orderNo": 1, "keyword": "input"}]),
    ]
    repository = FakeUiRunRepository(cases)

    await UiTestCaseRunService(repository).run_suite("user-1", "suite-1", RunUiSuiteRequest())

    run = next(row for row in repository.rows if isinstance(row, UiTestSuiteRun))
    items = [row for row in repository.rows if isinstance(row, UiTestSuiteRunItem)]
    assert run.snapshot_json["suiteRunId"] == run.suite_run_id
    assert run.snapshot_json["suite"]["name"] == "xiaoming"
    assert "items" not in run.snapshot_json
    assert [item.snapshot_json["caseId"] for item in items] == [
        "case-1",
        "case-2",
    ]
    assert [item.snapshot_json["itemId"] for item in items] == [item.item_id for item in items]
    assert [item.snapshot_json["case"]["stepsJson"] for item in items] == [
        [{"orderNo": 1, "keyword": "open"}],
        [{"orderNo": 1, "keyword": "input"}],
    ]


@pytest.mark.asyncio
async def test_suite_report_returns_item_execution_results():
    repository = FakeUiRunRepository([])
    repository.suite_run = SimpleNamespace(
        suite_run_id="suite-run-1",
        suite_id="suite-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="failed",
        total_count=1,
        success_count=0,
        failed_count=1,
        error_count=0,
        skipped_count=0,
        error_message="1个用例失败",
        started_at=None,
        finished_at=None,
        duration_ms=1200,
        created_at=None,
        updated_at=None,
    )
    repository.suite_items = [
        SimpleNamespace(
            item_id="item-1",
            case_id="case-1",
            snapshot_json={"case": {"name": "登录失败"}},
            status="failed",
            order_no=1,
            step_results_json=[{"orderNo": 1, "status": "failed"}],
            error_message="按钮不可见",
            duration_ms=1200,
            started_at=None,
            finished_at=None,
        )
    ]

    payload = await UiTestCaseRunService(repository).suite_report("user-1", "suite-run-1")

    assert payload["items"] == [
        {
            "itemId": "item-1",
            "caseId": "case-1",
            "caseName": "登录失败",
            "status": "failed",
            "orderNo": 1,
            "stepResults": [{"orderNo": 1, "status": "failed"}],
            "errorMessage": "按钮不可见",
            "durationMs": 1200,
            "startedAt": None,
            "finishedAt": None,
        }
    ]


class FakeCompletionSession:
    def __init__(self, run):
        self.run = run

    async def scalar(self, statement):
        return self.run


@pytest.mark.asyncio
async def test_case_completion_preserves_execution_snapshot():
    run = SimpleNamespace(
        status="running",
        snapshot_json={"runId": "run-1", "case": {"caseId": "case-1"}},
        step_results_json=[],
        error_message="",
        finished_at=None,
        duration_ms=0,
    )
    task = SimpleNamespace(task_type="case_debug", run_id="run-1")

    await complete_domain_run(
        FakeCompletionSession(run),
        "ui",
        task,
        WorkerTaskEventRequest(
            workerId="worker-1",
            status="success",
            snapshotJson={"browser": "chromium"},
            stepResults=[{"orderNo": 1, "status": "success"}],
        ),
    )

    assert run.snapshot_json == {
        "runId": "run-1",
        "case": {"caseId": "case-1"},
    }
    assert run.step_results_json == [{"orderNo": 1, "status": "success"}]


@pytest.mark.asyncio
async def test_suite_completion_preserves_execution_snapshot_without_summary_json():
    run = SimpleNamespace(
        status="running",
        snapshot_json={"suiteRunId": "run-1"},
        error_message="",
        finished_at=None,
        duration_ms=0,
    )
    task = SimpleNamespace(task_type="suite_run", run_id="run-1")

    await complete_domain_run(
        FakeCompletionSession(run),
        "ui",
        task,
        WorkerTaskEventRequest(
            workerId="worker-1",
            status="success",
            snapshotJson={"successCount": 2, "failedCount": 0},
        ),
    )

    assert run.snapshot_json == {
        "suiteRunId": "run-1",
    }


def worker_task(task_type):
    return SimpleNamespace(
        task_id="worker-task-1",
        task_type=task_type,
        domain="ui",
        run_id="run-1",
        suite_id="suite-1",
        case_id="case-1" if task_type == "case_debug" else "",
        collection_run_id="",
        collection_id="",
        generate_task_id="",
        status="claimed",
    )


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class SnapshotOnlySession:
    def __init__(self, run, items=None):
        self.run = run
        self.items = items or []
        self.scalar_calls = 0
        self.scalars_calls = 0

    async def scalar(self, statement):
        self.scalar_calls += 1
        return self.run

    async def scalars(self, statement):
        self.scalars_calls += 1
        return FakeScalars(self.items)


@pytest.mark.asyncio
async def test_case_snapshot_reads_only_case_run_snapshot_json():
    snapshot = {
        "runId": "run-1",
        "suite": {"suiteId": "suite-1", "name": "xiaoming"},
        "case": {
            "caseId": "case-1",
            "name": "登录成功",
            "stepsJson": [{"orderNo": 1, "keyword": "open"}],
        },
    }
    session = SnapshotOnlySession(SimpleNamespace(snapshot_json=snapshot))

    payload = await build_snapshot(session, "ui", worker_task("case_debug"))

    assert session.scalar_calls == 1
    assert payload["caseRun"]["case"]["stepsJson"] == [{"orderNo": 1, "keyword": "open"}]
    assert snapshot["case"]["stepsJson"] == [{"orderNo": 1, "keyword": "open"}]
    assert "snapshot" not in payload["caseRun"]


@pytest.mark.asyncio
async def test_suite_snapshot_combines_suite_run_and_item_snapshots():
    snapshot = {
        "suiteRunId": "run-1",
        "suite": {"suiteId": "suite-1", "name": "xiaoming"},
    }
    item_snapshot = {
        "itemId": "item-1",
        "caseId": "case-1",
        "case": {
            "caseId": "case-1",
            "stepsJson": [{"orderNo": 1, "keyword": "open"}],
        },
    }
    session = SnapshotOnlySession(
        SimpleNamespace(snapshot_json=snapshot),
        [SimpleNamespace(snapshot_json=item_snapshot)],
    )

    payload = await build_snapshot(session, "ui", worker_task("suite_run"))

    assert session.scalar_calls == 1
    assert session.scalars_calls == 1
    assert payload["suiteRun"]["items"][0]["case"]["stepsJson"] == [
        {"orderNo": 1, "keyword": "open"}
    ]
    assert item_snapshot["case"]["stepsJson"] == [{"orderNo": 1, "keyword": "open"}]
    assert "snapshot" not in payload["suiteRun"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_type", "payload_key"),
    [
        ("case_debug", "caseRun"),
        ("suite_run", "suiteRun"),
    ],
)
async def test_ui_snapshot_does_not_fallback_when_run_snapshot_is_empty(
    task_type,
    payload_key,
):
    session = SnapshotOnlySession(SimpleNamespace(snapshot_json={}))

    payload = await build_snapshot(session, "ui", worker_task(task_type))

    assert session.scalar_calls == 1
    expected = {"items": []} if task_type == "suite_run" else {}
    assert payload[payload_key] == expected
