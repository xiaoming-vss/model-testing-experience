from __future__ import annotations

from typing import Any

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.schemas.ui_run import (
    DebugRunUiCaseRequest,
    RunUiSuiteRequest,
    UiCaseRunResponse,
    UiSuiteRunResponse,
)
from testing_agent.services.common import dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access
from testing_agent.services.ui_execution_payload import ui_case_payload, ui_suite_payload


class UiCaseRunContext:
    def __init__(
        self,
        case: UiTestCase,
        suite: UiTestSuite,
        requirement: Requirement,
        sprint: Sprint,
        project: Project,
    ):
        self.case = case
        self.suite = suite
        self.requirement = requirement
        self.sprint = sprint
        self.project = project


class UiSuiteRunContext:
    def __init__(
        self,
        suite: UiTestSuite,
        requirement: Requirement,
        sprint: Sprint,
        project: Project,
    ):
        self.suite = suite
        self.requirement = requirement
        self.sprint = sprint
        self.project = project


def apply_run_scope(run, context):
    run.requirement_id = context.requirement.requirement_id
    run.sprint_id = context.sprint.sprint_id
    run.project_id = context.project.project_id


def dump_case_run(run: UiTestCaseRun) -> dict:
    data = dump(UiCaseRunResponse, run)
    data["success"] = run.status in {"success", "passed", "completed"}
    return data


def dump_suite_run(run: UiTestSuiteRun) -> dict:
    data = dump(UiSuiteRunResponse, run)
    data["success"] = run.status in {"success", "passed", "completed"}
    return data


def suite_run_item_case_name(item: UiTestSuiteRunItem) -> str:
    snapshot = item.snapshot_json
    if not isinstance(snapshot, dict):
        return ""
    case_snapshot = snapshot.get("case")
    if not isinstance(case_snapshot, dict):
        return ""
    return str(case_snapshot.get("name") or "")


class UiTestCaseRunService:
    def __init__(self, repository: UiTestCaseRunRepository):
        self.repository = repository

    async def get_accessible_suite(
        self,
        user_id: str,
        suite_id: str,
        *,
        action: ProjectAction = "read",
    ) -> UiSuiteRunContext:
        suite = await self.repository.get_suite(suite_id)
        if suite is None:
            raise ErrNotFound
        requirement = await self.repository.get_requirement(suite.requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return UiSuiteRunContext(suite, requirement, sprint, project)

    async def get_accessible_case(
        self, user_id: str, case_id: str, *, action: ProjectAction = "read"
    ) -> UiCaseRunContext:
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ErrNotFound
        suite_context = await self.get_accessible_suite(user_id, case.suite_id, action=action)
        return UiCaseRunContext(
            case,
            suite_context.suite,
            suite_context.requirement,
            suite_context.sprint,
            suite_context.project,
        )

    async def debug_run_case(self, user_id: str, case_id: str, _: DebugRunUiCaseRequest) -> dict:
        context = await self.get_accessible_case(user_id, case_id, action="execute")
        run_id = new_id()
        run = UiTestCaseRun(
            run_id=run_id,
            case_id=context.case.case_id,
            suite_id=context.suite.suite_id,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=RunStatus.PENDING.value,
            snapshot_json={
                "runId": run_id,
                "suite": ui_suite_payload(context.suite),
                "case": ui_case_payload(context.case),
            },
            step_results_json=[],
        )
        task = WorkerTask(
            domain="ui",
            task_id=new_id(),
            task_type="case_debug",
            run_id=run.run_id,
            suite_id=context.suite.suite_id,
            case_id=context.case.case_id,
            status=RunStatus.PENDING.value,
        )
        self.repository.add_all([run, task])
        await self.repository.commit()
        await self.repository.refresh(run)
        apply_run_scope(run, context)
        return dump_case_run(run)

    async def get_case_run(self, user_id: str, run_id: str) -> dict:
        run = await self.repository.get_case_run(run_id)
        if run is None:
            raise ErrNotFound
        context = await self.get_accessible_suite(user_id, run.suite_id, action="read")
        apply_run_scope(run, context)
        return dump_case_run(run)

    async def run_suite(self, user_id: str, suite_id: str, _: RunUiSuiteRequest) -> dict:
        context = await self.get_accessible_suite(user_id, suite_id, action="execute")
        cases = await self.repository.list_cases(suite_id)
        suite_run_id = new_id()
        items = []
        for case in cases:
            item_id = new_id()
            item = UiTestSuiteRunItem(
                item_id=item_id,
                suite_run_id=suite_run_id,
                case_id=case.case_id,
                order_no=case.order_no,
                continue_on_failure=False,
                status=RunStatus.PENDING.value,
                snapshot_json={
                    "itemId": item_id,
                    "caseId": case.case_id,
                    "case": ui_case_payload(case),
                    "orderNo": case.order_no,
                    "continueOnFailure": False,
                    "status": "pending",
                },
            )
            items.append(item)
        run = UiTestSuiteRun(
            suite_run_id=suite_run_id,
            suite_id=suite_id,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=RunStatus.PENDING.value,
            total_count=len(cases),
            snapshot_json={
                "suiteRunId": suite_run_id,
                "suite": ui_suite_payload(context.suite),
            },
        )
        task = WorkerTask(
            domain="ui",
            task_id=new_id(),
            task_type="suite_run",
            run_id=run.suite_run_id,
            suite_id=suite_id,
            status=RunStatus.PENDING.value,
        )
        self.repository.add_all([run, task])
        await self.repository.flush()
        for item in items:
            self.repository.add(item)
        await self.repository.commit()
        await self.repository.refresh(run)
        apply_run_scope(run, context)
        return dump_suite_run(run)

    async def list_suite_runs(self, user_id: str, suite_id: str) -> dict[str, Any]:
        context = await self.get_accessible_suite(user_id, suite_id, action="read")
        rows = await self.repository.list_suite_runs(suite_id)
        for row in rows:
            apply_run_scope(row, context)
        return list_payload([dump_suite_run(row) for row in rows])

    async def get_suite_run(self, user_id: str, suite_run_id: str) -> dict:
        run = await self.repository.get_suite_run(suite_run_id)
        if run is None:
            raise ErrNotFound
        context = await self.get_accessible_suite(user_id, run.suite_id, action="read")
        apply_run_scope(run, context)
        return dump_suite_run(run)

    async def suite_report(self, user_id: str, suite_run_id: str) -> dict:
        run = await self.repository.get_suite_run(suite_run_id)
        if run is None:
            raise ErrNotFound
        context = await self.get_accessible_suite(user_id, run.suite_id, action="read")
        apply_run_scope(run, context)
        items = await self.repository.list_suite_items(suite_run_id)
        data = dump_suite_run(run)
        data["items"] = [
            {
                "itemId": item.item_id,
                "caseId": item.case_id,
                "caseName": suite_run_item_case_name(item),
                "status": item.status,
                "orderNo": item.order_no,
                "stepResults": item.step_results_json or [],
                "errorMessage": item.error_message,
                "durationMs": item.duration_ms,
                "startedAt": item.started_at,
                "finishedAt": item.finished_at,
            }
            for item in items
        ]
        return data
