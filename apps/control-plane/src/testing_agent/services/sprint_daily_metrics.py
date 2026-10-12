from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from testing_agent.core.enums import TestOrderEntryStatus
from testing_agent.core.errors import (
    ErrNotFound,
    ErrSprintDailyMetricsDateInvalid,
    ErrSprintDailyMetricsNotFound,
)
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access


@dataclass(slots=True)
class TestMetrics:
    total: int = 0
    executed: int = 0
    pending: int = 0
    success: int = 0
    failed: int = 0


@dataclass(slots=True)
class BugMetrics:
    total: int = 0
    resolved: int = 0
    closed: int = 0
    unresolved: int = 0
    fatal: int = 0
    serious: int = 0
    normal: int = 0
    suggestion: int = 0


def dump_metric(metric: SprintDailyMetrics) -> dict[str, Any]:
    return {
        "projectId": metric.project_id,
        "sprintId": metric.sprint_id,
        "snapshotDate": format_metric_date(metric.snapshot_date),
        "function": {
            "total": metric.function_case_total,
            "executed": metric.function_case_executed,
            "pending": metric.function_case_pending,
            "success": metric.function_case_success,
            "failed": metric.function_case_failed,
        },
        "api": {
            "total": metric.api_case_total,
            "executed": metric.api_case_executed,
            "pending": metric.api_case_pending,
            "success": metric.api_case_success,
            "failed": metric.api_case_failed,
        },
        "ui": {
            "total": metric.ui_case_total,
            "executed": metric.ui_case_executed,
            "pending": metric.ui_case_pending,
            "success": metric.ui_case_success,
            "failed": metric.ui_case_failed,
        },
        "bug": {
            "total": metric.bug_total,
            "resolved": metric.bug_resolved,
            "closed": metric.bug_closed,
            "unresolved": metric.bug_unresolved,
            "fatal": metric.bug_fatal,
            "serious": metric.bug_serious,
            "normal": metric.bug_normal,
            "suggestion": metric.bug_suggestion,
        }
        if metric.bug_metrics_collected is not False
        else None,
        "createdAt": metric.created_at,
        "updatedAt": metric.updated_at,
    }


class SprintDailyMetricsService:
    def __init__(
        self,
        repository: SprintDailyMetricsRepository,
        integration_connection_service: Any | None = None,
        zentao_resource_client: Any | None = None,
    ):
        self.repository = repository
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client

    async def get_accessible_sprint(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> Sprint:
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None:
            raise ErrNotFound()
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, action)
        return sprint

    async def list(
        self,
        sprint_id: str,
        user_id: str,
        start_date: str = "",
        end_date: str = "",
    ) -> dict[str, Any]:
        if start_date:
            validate_sprint_daily_metrics_date(start_date)
        if end_date:
            validate_sprint_daily_metrics_date(end_date)
        await self.get_accessible_sprint(user_id, sprint_id, action="read")
        rows = await self.repository.list(sprint_id, start_date, end_date)
        return list_payload([dump_metric(row) for row in rows])

    async def get(self, sprint_id: str, snapshot_date: str, user_id: str) -> dict:
        validate_sprint_daily_metrics_date(snapshot_date)
        sprint = await self.get_accessible_sprint(user_id, sprint_id, action="read")
        metric = await self.repository.get(sprint_id, snapshot_date)
        if metric is None:
            raise ErrSprintDailyMetricsNotFound()
        return await self.dump_metric_detail(user_id, metric, sprint)

    async def upsert(
        self,
        sprint_id: str,
        snapshot_date: str,
        connection_id: str | None,
        user_id: str,
    ) -> dict:
        validate_sprint_daily_metrics_date(snapshot_date)
        sprint = await self.get_accessible_sprint(user_id, sprint_id, action="write")
        metric = await self.repository.get(sprint_id, snapshot_date)
        if metric is None:
            metric = SprintDailyMetrics(
                project_id=sprint.project_id,
                sprint_id=sprint_id,
                snapshot_date=snapshot_date,
            )
            self.repository.add(metric)

        await self.apply_snapshot_metrics(
            user_id,
            sprint,
            metric,
            connection_id=connection_id or "",
        )
        await self.repository.commit()
        await self.repository.refresh(metric)
        return await self.dump_metric_detail(user_id, metric, sprint)

    async def dump_metric_detail(
        self,
        user_id: str,
        metric: SprintDailyMetrics,
        sprint: Sprint,
    ) -> dict[str, Any]:
        project = await self.repository.get_project(metric.project_id or sprint.project_id)
        requirements = await self.repository.list_requirements_by_sprint(sprint.sprint_id)
        bugs = (metric.bug_details_json or []) if metric.bug_metrics_collected is not False else []
        result = dump_metric(metric)
        result.update(
            {
                "project": {
                    "projectName": str(getattr(project, "name", "") or ""),
                    "description": str(getattr(project, "description", "") or ""),
                },
                "sprint": {
                    "sprintName": str(getattr(sprint, "name", "") or ""),
                    "startDate": format_metric_date(getattr(sprint, "start_time", None)),
                    "endDate": format_metric_date(getattr(sprint, "end_time", None)),
                    "description": str(getattr(sprint, "description", "") or ""),
                },
                "requirements": [
                    {
                        "requirementName": str(getattr(item, "name", "") or ""),
                        "description": str(getattr(item, "document_content", "") or ""),
                    }
                    for item in requirements
                ],
                "bugs": bugs,
            }
        )
        return result

    async def apply_snapshot_metrics(
        self, user_id: str, sprint: Sprint, metric: SprintDailyMetrics, *, connection_id: str = ""
    ) -> None:
        function_metrics = await self.load_function_metrics_from_local_runs(sprint.sprint_id)
        api_metrics = await self.load_api_metrics_from_local_runs(sprint.sprint_id)
        ui_metrics = await self.load_ui_metrics_from_local_runs(sprint.sprint_id)
        bugs = await self.repository.list_bug_snapshots(sprint.project_id, sprint.sprint_id)
        bug_metrics = BugMetrics(
            total=len(bugs),
            resolved=sum(bug["status"] == "resolved" for bug in bugs),
            closed=sum(bug["status"] == "closed" for bug in bugs),
            unresolved=sum(bug["status"] == "active" for bug in bugs),
            fatal=sum(bug["severity"] == "fatal" for bug in bugs),
            serious=sum(bug["severity"] == "serious" for bug in bugs),
            normal=sum(bug["severity"] == "normal" for bug in bugs),
            suggestion=sum(bug["severity"] == "minor" for bug in bugs),
        )
        metric.bug_metrics_collected = True
        metric.bug_details_json = [dict(bug) for bug in bugs]

        metric.project_id = sprint.project_id
        metric.function_case_total = function_metrics.total
        metric.function_case_executed = function_metrics.executed
        metric.function_case_pending = function_metrics.pending
        metric.function_case_success = function_metrics.success
        metric.function_case_failed = function_metrics.failed
        metric.api_case_total = api_metrics.total
        metric.api_case_executed = api_metrics.executed
        metric.api_case_pending = api_metrics.pending
        metric.api_case_success = api_metrics.success
        metric.api_case_failed = api_metrics.failed
        metric.ui_case_total = ui_metrics.total
        metric.ui_case_executed = ui_metrics.executed
        metric.ui_case_pending = ui_metrics.pending
        metric.ui_case_success = ui_metrics.success
        metric.ui_case_failed = ui_metrics.failed
        metric.bug_total = bug_metrics.total
        metric.bug_resolved = bug_metrics.resolved
        metric.bug_closed = bug_metrics.closed
        metric.bug_unresolved = bug_metrics.unresolved
        metric.bug_fatal = bug_metrics.fatal
        metric.bug_serious = bug_metrics.serious
        metric.bug_normal = bug_metrics.normal
        metric.bug_suggestion = bug_metrics.suggestion

    async def load_function_metrics_from_local_runs(self, sprint_id: str) -> TestMetrics:
        """功能用例指标来自测试单条目的本地执行记录；阻塞与失败都算「未通过」。"""
        statuses = await self.repository.list_function_entry_statuses_by_sprint(sprint_id)
        metrics = TestMetrics()
        for status in statuses:
            metrics.total += 1
            if status == TestOrderEntryStatus.PENDING.value:
                continue
            metrics.executed += 1
            if status == TestOrderEntryStatus.PASSED.value:
                metrics.success += 1
            else:
                metrics.failed += 1
        metrics.pending = metrics.total - metrics.executed
        return metrics

    async def load_api_metrics_from_local_runs(self, sprint_id: str) -> TestMetrics:
        case_ids = await self.repository.list_api_case_ids_by_sprint(sprint_id)
        statuses = await self.repository.list_latest_api_run_statuses(sprint_id)
        return build_run_metrics(case_ids, statuses)

    async def load_ui_metrics_from_local_runs(self, sprint_id: str) -> TestMetrics:
        runs = await self.repository.list_latest_ui_suite_runs(sprint_id)
        metrics = TestMetrics()
        for run in runs:
            metrics.total += int_or_zero(run.total_count)
            metrics.success += int_or_zero(run.success_count)
            metrics.failed += int_or_zero(run.failed_count) + int_or_zero(run.error_count)
            metrics.executed += (
                int_or_zero(run.success_count)
                + int_or_zero(run.failed_count)
                + int_or_zero(run.error_count)
                + int_or_zero(run.skipped_count)
            )
        metrics.pending = max(metrics.total - metrics.executed, 0)
        return metrics


def build_run_metrics(case_ids: builtins.list[str], statuses: dict[str, str]) -> TestMetrics:
    metrics = TestMetrics(total=len(case_ids))
    for case_id in case_ids:
        match normalize_status(statuses.get(case_id, "")):
            case "success":
                metrics.executed += 1
                metrics.success += 1
            case "failed" | "error" | "timeout" | "canceled":
                metrics.executed += 1
                metrics.failed += 1
    metrics.pending = metrics.total - metrics.executed
    return metrics


def format_metric_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    return text[:10] if text else ""


def validate_sprint_daily_metrics_date(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ErrSprintDailyMetricsDateInvalid() from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ErrSprintDailyMetricsDateInvalid()


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
