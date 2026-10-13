from datetime import date, datetime
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


class FakeSprintDailyMetricsRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.bugs = []
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

    async def list_bug_snapshots(self, project_id, sprint_id):
        assert (project_id, sprint_id) == ("p1", "s1")
        return self.bugs

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == "s1" else None

    async def lock_sprint(self, sprint_id):
        return await self.get_sprint(sprint_id)

    async def get_project(self, project_id):
        return self.project if project_id == "p1" else None

    async def list(self, sprint_id, start_date="", end_date=""):
        return []

    async def get(self, sprint_id, snapshot_date, *, for_update=False):
        return self.metric

    async def list_requirements_by_sprint(self, sprint_id):
        return self.requirements if sprint_id == "s1" else []

    async def list_api_case_ids_by_sprint(self, sprint_id):
        return ["api-1", "api-2", "api-3"]

    async def list_latest_api_run_statuses(self, sprint_id):
        return {"api-1": "success", "api-2": "failed", "api-3": "pending"}

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

    def add(self, metric):
        self.metric = metric
        self.added = metric

    async def commit(self):
        self.committed = True

    async def refresh(self, metric):
        return None

    async def list_function_entry_statuses_by_sprint(self, sprint_id):
        return list(self.function_entry_statuses)


@pytest.mark.asyncio
async def test_sprint_daily_metrics_upsert_builds_snapshot_from_sources():
    repository = FakeSprintDailyMetricsRepository()
    # 功能用例指标来自本地测试单条目：下面三条状态推导出 3/2/1 与 1 通过 1 未通过。
    repository.function_entry_statuses = ["passed", "failed", "pending"]
    service = SprintDailyMetricsService(repository)

    result = await service.upsert("s1", "2026-01-23", None, "u1")

    assert repository.committed is True
    assert isinstance(repository.added, SprintDailyMetrics)
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
    assert result["bug"] == dict.fromkeys(
        ["total", "resolved", "closed", "unresolved", "fatal", "serious", "normal", "suggestion"], 0
    )
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
    assert result["bugs"] == []
    assert "metrics" not in result


@pytest.mark.asyncio
async def test_sprint_daily_metrics_get_returns_detail_context():
    repository = FakeSprintDailyMetricsRepository()
    repository.metric = SprintDailyMetrics(
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
async def test_sprint_daily_metrics_with_no_local_function_executions():
    repository = FakeSprintDailyMetricsRepository()
    service = SprintDailyMetricsService(repository)

    result = await service.upsert("s1", "2026-01-23", None, "u1")

    assert result["function"]["total"] == 0
    assert result["bug"] == dict.fromkeys(
        ["total", "resolved", "closed", "unresolved", "fatal", "serious", "normal", "suggestion"], 0
    )
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


@pytest.mark.asyncio
async def test_snapshot_never_uses_retired_external_connections():
    class RetiredExternalAccess:
        def __getattr__(self, name):
            raise AssertionError(f"Retired external collection accessed {name}")

    repository = FakeSprintDailyMetricsRepository()
    repository.function_entry_statuses = ["passed", "pending"]
    retired = RetiredExternalAccess()
    service = SprintDailyMetricsService(repository, retired, retired)
    result = await service.upsert("s1", "2026-01-23", "old-connection", "u1")
    assert repository.committed
    assert result["function"]["total"] == 2
    assert result["api"]["total"] == 3
    assert result["ui"]["total"] == 2
    assert result["bug"] == dict.fromkeys(
        ["total", "resolved", "closed", "unresolved", "fatal", "serious", "normal", "suggestion"], 0
    )
    assert result["bugs"] == []
    assert (await service.get("s1", "2026-01-23", "u1"))["bug"] == result["bug"]


@pytest.mark.asyncio
async def test_local_collection_failure_still_propagates():
    repository = FakeSprintDailyMetricsRepository()

    async def fail(_sprint_id):
        raise RuntimeError("local database failure")

    repository.list_function_entry_statuses_by_sprint = fail
    with pytest.raises(RuntimeError, match="local database failure"):
        await SprintDailyMetricsService(repository).upsert("s1", "2026-01-23", None, "u1")
    assert not repository.committed


@pytest.mark.asyncio
async def test_platform_bug_statistics_and_details_are_frozen_until_refresh():
    repository = FakeSprintDailyMetricsRepository()
    repository.bugs = [
        dict(
            bugId="b1", bugNo=1, title="重新激活", status="active", severity="fatal", resolution=""
        ),
        dict(
            bugId="b2",
            bugNo=2,
            title="延期",
            status="resolved",
            severity="serious",
            resolution="postponed",
        ),
        dict(
            bugId="b3",
            bugNo=3,
            title="关闭",
            status="closed",
            severity="normal",
            resolution="fixed",
        ),
        dict(bugId="b4", bugNo=4, title="轻微", status="active", severity="minor", resolution=""),
    ]
    service = SprintDailyMetricsService(repository)
    result = await service.upsert("s1", "2026-01-23", None, "u1")
    assert result["bug"] == dict(
        total=4, resolved=1, closed=1, unresolved=2, fatal=1, serious=1, normal=1, suggestion=1
    )
    assert result["bugs"] == repository.bugs
    repository.bugs[0]["status"] = "closed"
    frozen = await service.get("s1", "2026-01-23", "u1")
    assert frozen["bugs"][0]["status"] == "active"
    assert frozen["bug"] == result["bug"]
    refreshed = await service.upsert("s1", "2026-01-23", None, "u1")
    assert refreshed["bug"]["closed"] == 2
    assert refreshed["bug"]["unresolved"] == 1


@pytest.mark.asyncio
async def test_bug_query_failure_does_not_commit_zero_snapshot():
    repository = FakeSprintDailyMetricsRepository()

    async def fail(project_id, sprint_id):
        raise RuntimeError("bug query failed")

    repository.list_bug_snapshots = fail
    with pytest.raises(RuntimeError, match="bug query failed"):
        await SprintDailyMetricsService(repository).upsert("s1", "2026-01-23", None, "u1")
    assert not repository.committed
