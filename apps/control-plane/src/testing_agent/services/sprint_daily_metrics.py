from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from testing_agent.core.errors import (
    ErrNotFound,
    ErrResourceBindingInvalid,
    ErrSprintDailyMetricsDateInvalid,
    ErrSprintDailyMetricsNotFound,
    ErrZentaoRemoteResourceUnavailable,
    dynamic_error,
)
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.common import list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access
from testing_agent.services.zentao_resource import parse_zentao_remote_id, truncate_error


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
        },
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
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
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
            raise ErrSprintDailyMetricsNotFound
        return await self.dump_metric_detail(user_id, metric, sprint)

    async def upsert(
        self,
        sprint_id: str,
        snapshot_date: str,
        _body: dict[str, Any] | None,
        user_id: str,
    ) -> dict:
        validate_sprint_daily_metrics_date(snapshot_date)
        sprint = await self.get_accessible_sprint(user_id, sprint_id, action="write")
        metric = await self.repository.get(sprint_id, snapshot_date)
        if metric is None:
            metric = SprintDailyMetrics(
                metric_id=f"{sprint_id}-{snapshot_date}",
                project_id=sprint.project_id,
                sprint_id=sprint_id,
                snapshot_date=snapshot_date,
            )
            self.repository.add(metric)

        await self.apply_snapshot_metrics(
            user_id,
            sprint,
            metric,
            connection_id=str(
                (_body or {}).get("connectionId") or (_body or {}).get("connection_id") or ""
            ),
        )
        metric.bug_details_json = await self.load_bug_details_from_execution(
            user_id,
            sprint.sprint_id,
            connection_id=str(
                (_body or {}).get("connectionId") or (_body or {}).get("connection_id") or ""
            ),
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
        bugs = metric.bug_details_json or []
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
        function_metrics = await self.load_function_metrics_from_execution(
            user_id, sprint.sprint_id, connection_id=connection_id
        )
        api_metrics = await self.load_api_metrics_from_local_runs(sprint.sprint_id)
        ui_metrics = await self.load_ui_metrics_from_local_runs(sprint.sprint_id)
        bug_metrics = await self.load_bug_metrics_from_execution(
            user_id, sprint.sprint_id, connection_id=connection_id
        )

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

    async def load_function_metrics_from_execution(
        self, user_id: str, sprint_id: str, *, connection_id: str = ""
    ) -> TestMetrics:
        access = await self.resolve_execution_binding_access(
            user_id, sprint_id, connection_id=connection_id
        )
        if access is None:
            return TestMetrics()
        connection, remote_execution_id = access
        metrics = TestMetrics()
        page = 1
        page_size = 100
        while True:
            if self.zentao_resource_client is None:
                raise ErrZentaoRemoteResourceUnavailable
            result = await self.call_zentao(
                self.zentao_resource_client.list_execution_cases,
                connection,
                remote_execution_id,
                page,
                page_size,
            )
            items = list_items(result)
            for item in items:
                if bool(item_value(item, "deleted", default=False)):
                    continue
                metrics.total += 1
                match normalize_status(item_value(item, "last_run_result", "lastRunResult")):
                    case "":
                        pass
                    case "pass":
                        metrics.executed += 1
                        metrics.success += 1
                    case _:
                        metrics.executed += 1
                        metrics.failed += 1
            if is_last_page(result, page, page_size, len(items)):
                break
            page += 1
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

    async def load_bug_metrics_from_execution(
        self, user_id: str, sprint_id: str, *, connection_id: str = ""
    ) -> BugMetrics:
        access = await self.resolve_execution_binding_access(
            user_id, sprint_id, connection_id=connection_id
        )
        if access is None:
            return BugMetrics()
        connection, remote_execution_id = access
        metrics = BugMetrics()
        page = 1
        page_size = 100
        while True:
            if self.zentao_resource_client is None:
                raise ErrZentaoRemoteResourceUnavailable
            result = await self.call_zentao(
                self.zentao_resource_client.list_execution_bugs,
                connection,
                remote_execution_id,
                page,
                page_size,
            )
            items = list_items(result)
            for item in items:
                metrics.total += 1
                status = normalize_status(item_value(item, "status"))
                if is_closed_bug_status(status):
                    metrics.closed += 1
                if is_resolved_bug_status(status):
                    metrics.resolved += 1
                else:
                    metrics.unresolved += 1
                match int_or_zero(item_value(item, "severity")):
                    case 1:
                        metrics.fatal += 1
                    case 2:
                        metrics.serious += 1
                    case 3:
                        metrics.normal += 1
                    case 4:
                        metrics.suggestion += 1
            if is_last_page(result, page, page_size, len(items)):
                break
            page += 1
        return metrics

    async def load_bug_details_from_execution(
        self, user_id: str, sprint_id: str, *, connection_id: str = ""
    ) -> builtins.list[dict[str, str]]:
        if self.integration_connection_service is None or self.zentao_resource_client is None:
            return []
        access = await self.resolve_execution_binding_access(
            user_id, sprint_id, connection_id=connection_id
        )
        if access is None:
            return []
        connection, remote_execution_id = access
        bugs: builtins.list[dict[str, str]] = []
        page = 1
        page_size = 100
        while True:
            if self.zentao_resource_client is None:
                raise ErrZentaoRemoteResourceUnavailable
            result = await self.call_zentao(
                self.zentao_resource_client.list_execution_bugs,
                connection,
                remote_execution_id,
                page,
                page_size,
            )
            items = list_items(result)
            bugs.extend(dump_bug_detail(item) for item in items)
            if is_last_page(result, page, page_size, len(items)):
                break
            page += 1
        return bugs

    async def resolve_execution_binding_access(
        self, user_id: str, sprint_id: str, *, connection_id: str = ""
    ) -> tuple[Any, str] | None:
        binding = await self.repository.get_active_binding("sprint", sprint_id)
        if binding is None:
            return None
        validate_zentao_execution_binding(binding)
        try:
            remote_execution_id = str(parse_zentao_remote_id(binding.remote_resource_id))
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc
        if self.integration_connection_service is None or self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable
        sprint = await self.repository.get_sprint(sprint_id)
        if sprint is None:
            raise ErrNotFound
        selected = await self.integration_connection_service.resolve_personal_connection(
            user_id, "zentao", sprint.project_id, binding.instance_url, connection_id
        )
        connection = await self.integration_connection_service.resolve_zentao_access(
            user_id, selected.connection_id, sprint.project_id
        )
        return connection, remote_execution_id

    async def call_zentao(self, method: Any, *args: Any) -> dict[str, Any]:
        try:
            return await method(*args)
        except Exception as exc:
            raise dynamic_error(
                ErrZentaoRemoteResourceUnavailable,
                truncate_error(str(exc)),
            ) from exc


def dump_bug_detail(item: Any) -> dict[str, str]:
    return {
        "title": string_item_value(item, "title", "name"),
        "module": string_item_value(item, "module", "moduleName", "module_name"),
        "severity": normalize_bug_severity(item_value(item, "severity")),
        "status": string_item_value(item, "status"),
        "owner": string_item_value(
            item,
            "owner",
            "assignedTo",
            "assigned_to",
            "openedBy",
            "opened_by",
        ),
        "description": string_item_value(item, "description", "desc", "steps"),
    }


def normalize_bug_severity(value: Any) -> str:
    text = str(value or "").strip()
    return {"1": "致命", "2": "严重", "3": "一般", "4": "建议"}.get(text, text)


def string_item_value(item: Any, *names: str) -> str:
    return str(item_value(item, *names, default="") or "")


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
        raise ErrSprintDailyMetricsDateInvalid from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ErrSprintDailyMetricsDateInvalid


def validate_zentao_execution_binding(binding: ResourceBinding) -> None:
    if binding.provider != "zentao" or binding.remote_resource_type not in {"execution", "sprint"}:
        raise dynamic_error(ErrResourceBindingInvalid, "资源绑定不是有效的禅道执行绑定")


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def is_resolved_bug_status(status: Any) -> bool:
    return normalize_status(status) in {"resolved", "closed"}


def is_closed_bug_status(status: Any) -> bool:
    return normalize_status(status) == "closed"


def item_value(item: Any, *names: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        for name in names:
            if name in item:
                return item[name]
        return default
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    return default


def list_items(result: dict[str, Any]) -> builtins.list[Any]:
    items = result.get("items", [])
    return items if isinstance(items, list) else []


def is_last_page(result: dict[str, Any], page: int, page_size: int, item_count: int) -> bool:
    total = int_or_zero(result.get("total"))
    return item_count < page_size or (total > 0 and page * page_size >= total)


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
