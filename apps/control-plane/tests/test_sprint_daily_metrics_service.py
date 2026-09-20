from datetime import date, datetime
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


class FakeSprintDailyMetricsRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.metric = None
        self.added = None
        self.committed = False
        # 功能用例的执行状态来自本地测试单条目（不再走禅道），由用例按需设置。
        self.function_entry_statuses: list[str] = []
        self.sprint = SimpleNamespace(
            sprint_id="s1",
            project_id="p1",
            name="2026年1月迭代",
            description="迭代描述",
            start_time=datetime(2026, 1, 1),
            end_time=datetime(2026, 1, 23),
        )
        self.project = SimpleNamespace(
            project_id="p1",
            user_id="u1",
            name="智慧园区管理平台",
            description="项目描述",
        )
        self.requirements = [
            SimpleNamespace(name="登录需求", document_content="登录能力说明"),
            SimpleNamespace(name="报表需求", document_content=""),
        ]
        self.binding = SimpleNamespace(
            provider="zentao",
            instance_url="http://zentao.local",
            connection_id="c1",
            remote_resource_type="execution",
            remote_resource_id="101",
        )

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == "s1" else None

    async def get_project(self, project_id):
        return self.project if project_id == "p1" else None

    async def list(self, sprint_id, start_date="", end_date=""):
        return []

    async def get(self, sprint_id, snapshot_date):
        return self.metric

    async def list_requirements_by_sprint(self, sprint_id):
        return self.requirements if sprint_id == "s1" else []

    async def list_api_case_ids_by_sprint(self, sprint_id):
        return ["api-1", "api-2", "api-3"]

    async def list_latest_api_run_statuses(self, sprint_id):
        return {"api-1": "success", "api-2": "failed", "api-3": "pending"}

    async def list_ui_case_ids_by_sprint(self, sprint_id):
        return ["ui-1", "ui-2"]

    async def list_latest_ui_suite_runs(self, sprint_id):
        return [
            SimpleNamespace(
                suite_id="suite-1",
                total_count=2,
                success_count=1,
                failed_count=1,
                error_count=0,
                skipped_count=0,
            )
        ]

    async def get_active_binding(self, resource_type, resource_id):
        return self.binding

    def add(self, metric):
        self.metric = metric
        self.added = metric

    async def commit(self):
        self.committed = True

    async def refresh(self, metric):
        return None

    async def list_function_entry_statuses_by_sprint(self, sprint_id):
        return list(self.function_entry_statuses)


class FakeIntegrationConnectionService:
    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        assert user_id == "u1"
        return SimpleNamespace(connection_id="c1")

    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        assert project_id in {"", "p1"}
        return SimpleNamespace(connection_id=connection_id)


class FakeZentaoResourceClient:
    async def list_execution_cases(self, connection, remote_execution_id, page, page_size):
        assert remote_execution_id == "101"
        return {
            "total": 4,
            "items": [
                {"deleted": False, "lastRunResult": "pass"},
                {"deleted": False, "lastRunResult": "fail"},
                {"deleted": False, "lastRunResult": ""},
                {"deleted": True, "lastRunResult": "pass"},
            ],
        }

    async def list_execution_bugs(self, connection, remote_execution_id, page, page_size):
        assert remote_execution_id == "101"
        return {
            "total": 3,
            "items": [
                {
                    "title": "登录失败",
                    "module": "账号模块",
                    "severity": 1,
                    "status": "resolved",
                    "owner": "tester-a",
                    "description": "输入正确密码仍提示失败",
                },
                {
                    "name": "报表样式错位",
                    "moduleName": "报表模块",
                    "severity": 4,
                    "status": "active",
                    "assignedTo": "tester-b",
                    "desc": "表格列宽异常",
                },
                {
                    "title": "导出失败",
                    "module": "报表模块",
                    "severity": 3,
                    "status": "closed",
                    "openedBy": "tester-c",
                    "steps": "点击导出后报错",
                },
            ],
        }


@pytest.mark.asyncio
async def test_sprint_daily_metrics_upsert_builds_snapshot_from_sources():
    repository = FakeSprintDailyMetricsRepository()
    # 功能用例指标来自本地测试单条目：下面三条状态推导出 3/2/1 与 1 通过 1 未通过。
    repository.function_entry_statuses = ["passed", "failed", "pending"]
    service = SprintDailyMetricsService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    result = await service.upsert("s1", "2026-01-23", None, "u1")

    assert repository.committed is True
    assert isinstance(repository.added, SprintDailyMetrics)
    assert repository.added.metric_id == "s1-2026-01-23"
    assert result["function"] == {
        "total": 3,
        "executed": 2,
        "pending": 1,
        "success": 1,
        "failed": 1,
    }
    assert result["api"] == {
        "total": 3,
        "executed": 2,
        "pending": 1,
        "success": 1,
        "failed": 1,
    }
    assert result["ui"] == {
        "total": 2,
        "executed": 2,
        "pending": 0,
        "success": 1,
        "failed": 1,
    }
    assert result["bug"] == {
        "total": 3,
        "resolved": 2,
        "closed": 1,
        "unresolved": 1,
        "fatal": 1,
        "serious": 0,
        "normal": 1,
        "suggestion": 1,
    }
    assert result["project"] == {
        "projectName": "智慧园区管理平台",
        "description": "项目描述",
    }
    assert result["sprint"] == {
        "sprintName": "2026年1月迭代",
        "startDate": "2026-01-01",
        "endDate": "2026-01-23",
        "description": "迭代描述",
    }
    assert result["requirements"] == [
        {"requirementName": "登录需求", "description": "登录能力说明"},
        {"requirementName": "报表需求", "description": ""},
    ]
    assert result["bugs"] == [
        {
            "title": "登录失败",
            "module": "账号模块",
            "severity": "致命",
            "status": "resolved",
            "owner": "tester-a",
            "description": "输入正确密码仍提示失败",
        },
        {
            "title": "报表样式错位",
            "module": "报表模块",
            "severity": "建议",
            "status": "active",
            "owner": "tester-b",
            "description": "表格列宽异常",
        },
        {
            "title": "导出失败",
            "module": "报表模块",
            "severity": "一般",
            "status": "closed",
            "owner": "tester-c",
            "description": "点击导出后报错",
        },
    ]
    assert "metrics" not in result


@pytest.mark.asyncio
async def test_sprint_daily_metrics_get_returns_detail_context():
    repository = FakeSprintDailyMetricsRepository()
    repository.metric = SprintDailyMetrics(
        metric_id="m1",
        project_id="p1",
        sprint_id="s1",
        snapshot_date=date(2026, 1, 23),
        function_case_total=1,
        function_case_executed=1,
        function_case_pending=0,
        function_case_success=1,
        function_case_failed=0,
        api_case_total=2,
        api_case_executed=1,
        api_case_pending=1,
        api_case_success=1,
        api_case_failed=0,
        ui_case_total=3,
        ui_case_executed=2,
        ui_case_pending=1,
        ui_case_success=1,
        ui_case_failed=1,
        bug_total=4,
        bug_resolved=2,
        bug_closed=1,
        bug_unresolved=2,
        bug_fatal=1,
        bug_serious=1,
        bug_normal=1,
        bug_suggestion=1,
    )
    service = SprintDailyMetricsService(repository)

    result = await service.get("s1", "2026-01-23", "u1")

    assert result["snapshotDate"] == "2026-01-23"
    assert result["project"]["projectName"] == "智慧园区管理平台"
    assert result["sprint"]["startDate"] == "2026-01-01"
    assert result["requirements"][0] == {
        "requirementName": "登录需求",
        "description": "登录能力说明",
    }
    assert result["bugs"] == []
    assert "metrics" not in result


@pytest.mark.asyncio
async def test_sprint_daily_metrics_without_execution_binding_uses_zero_remote_metrics():
    repository = FakeSprintDailyMetricsRepository()
    repository.binding = None
    service = SprintDailyMetricsService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
    )

    result = await service.upsert("s1", "2026-01-23", {}, "u1")

    assert result["function"]["total"] == 0
    assert result["bug"]["total"] == 0
    assert result["api"]["total"] == 3
    assert result["ui"]["total"] == 2
    assert result["bugs"] == []


@pytest.mark.asyncio
async def test_ui_metrics_aggregate_latest_suite_run_counts():
    repository = FakeSprintDailyMetricsRepository()

    async def list_latest_ui_suite_runs(_sprint_id):
        return [
            SimpleNamespace(
                suite_id="suite-1",
                total_count=3,
                success_count=1,
                failed_count=0,
                error_count=1,
                skipped_count=1,
            ),
            SimpleNamespace(
                suite_id="suite-2",
                total_count=4,
                success_count=2,
                failed_count=1,
                error_count=0,
                skipped_count=0,
            ),
        ]

    repository.list_latest_ui_suite_runs = list_latest_ui_suite_runs
    service = SprintDailyMetricsService(repository)

    result = await service.load_ui_metrics_from_local_runs("s1")

    assert result.total == 7
    assert result.executed == 6
    assert result.pending == 1
    assert result.success == 3
    assert result.failed == 2
