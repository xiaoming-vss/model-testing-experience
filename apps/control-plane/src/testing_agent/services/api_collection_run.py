from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import (
    ErrApiCaseRunEnvironmentMismatch,
    ErrApiEnvironmentKindMismatch,
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.schemas.api_run import ApiCollectionRunResponse, RunApiCollectionRequest
from testing_agent.services.common import dump, paged_payload
from testing_agent.services.environment_access import authorized_environment_vars
from testing_agent.services.execution_secrets import protect_run
from testing_agent.services.project_access import ProjectAction, require_project_id


class ApiCollectionRunContext:
    def __init__(
        self,
        collection: ApiCollection,
        requirement: Requirement | None,
        sprint: Sprint | None,
        project: Project,
    ):
        self.collection = collection
        self.requirement = requirement
        self.sprint = sprint
        self.project = project


def dump_run(run: ApiCollectionRun) -> dict:
    data = dump(ApiCollectionRunResponse, run)
    data["success"] = run.status in {"success", "passed", "completed"}
    return data


def json_text(value: Any, default: str = "{}") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value or default
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_time(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


class ApiCollectionRunService:
    def __init__(self, repository: ApiCollectionRunRepository):
        self.repository = repository

    async def _resolve_requirement_scope(
        self, collection: ApiCollection, project_id: str
    ) -> tuple[Requirement | None, Sprint | None]:
        if collection.requirement_id is None:
            return None, None
        requirement = await self.repository.get_requirement(collection.requirement_id)
        if requirement is None:
            raise ErrNotFound()
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None or sprint.project_id != project_id:
            raise ErrNotFound()
        return requirement, sprint

    async def get_accessible_context(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> ApiCollectionRunContext:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound()
        project = await require_project_id(
            self.repository.session, user_id, collection.project_id, action=action
        )
        requirement, sprint = await self._resolve_requirement_scope(collection, project.project_id)
        return ApiCollectionRunContext(collection, requirement, sprint, project)

    async def ensure_owned_run(self, user_id: str, collection_run_id: str) -> ApiCollectionRun:
        run = await self.repository.get_run(collection_run_id)
        if run is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, run.project_id, action="read")
        return run

    async def run(self, user_id: str, collection_id: str, body: RunApiCollectionRequest) -> dict:
        context = await self.get_accessible_context(user_id, collection_id, action="execute")
        environment = await self.repository.get_environment(body.environment_id)
        if environment is None:
            raise ErrNotFound()
        if environment.project_id != context.project.project_id:
            raise ErrApiCaseRunEnvironmentMismatch()
        if environment.kind != "api":
            raise ErrApiEnvironmentKindMismatch()
        all_cases = await self.repository.list_cases(collection_id)
        cases = [case for case in all_cases if case.invalidated_at is None]
        if all_cases and not cases:
            raise dynamic_error(ErrBadRequest, "API 测试集没有有效用例")
        sprint = context.sprint
        if body.sprint_id is not None:
            requested_sprint = await self.repository.get_sprint(body.sprint_id)
            if (
                requested_sprint is None
                or requested_sprint.project_id != context.project.project_id
            ):
                raise dynamic_error(ErrBadRequest, "迭代不属于当前项目")
            sprint = requested_sprint
        env_vars = await authorized_environment_vars(
            self.repository.session, user_id, environment.environment_id
        )
        run = ApiCollectionRun(
            collection_run_id=new_id(),
            collection_id=collection_id,
            project_id=context.project.project_id,
            requirement_id=(
                context.requirement.requirement_id if context.requirement is not None else None
            ),
            requirement_name=(context.requirement.name if context.requirement is not None else ""),
            sprint_id=sprint.sprint_id if sprint is not None else None,
            sprint_name=sprint.name if sprint is not None else "",
            environment_id=environment.environment_id,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=RunStatus.PENDING.value,
            total_count=len(cases),
            success_count=0,
            failed_count=0,
            error_count=0,
            skipped_count=0,
            runtime_vars_json={},
            error_message="",
            duration_ms=0,
        )
        protect_run(run, [row.value for row in env_vars if row.is_secret])
        task = WorkerTask(
            domain="api",
            task_id=new_id(),
            task_type="api_collection_run",
            run_id=run.collection_run_id,
            status=RunStatus.PENDING.value,
        )
        self.repository.add_all([run, task])
        await self.repository.flush()
        for case in cases:
            self.repository.add(
                ApiCollectionRunItem(
                    item_id=new_id(),
                    collection_run_id=run.collection_run_id,
                    case_id=case.case_id,
                    order_no=case.order_no,
                    status=RunStatus.PENDING.value,
                    continue_on_failure=case.continue_on_failure,
                )
            )
        await self.repository.commit()
        from testing_agent.services.test_run_notifications import notify_task_available

        await notify_task_available()
        await self.repository.refresh(run)
        return dump_run(run)

    async def list(
        self, user_id: str, collection_id: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ErrBadRequest()
        await self.get_accessible_context(user_id, collection_id, action="read")
        rows, total = await self.repository.page_runs(collection_id, page, page_size)
        return paged_payload([dump_run(row) for row in rows], total)

    async def get(self, user_id: str, collection_run_id: str) -> dict:
        return dump_run(await self.ensure_owned_run(user_id, collection_run_id))

    async def report(self, user_id: str, collection_run_id: str) -> dict:
        run = await self.ensure_owned_run(user_id, collection_run_id)
        items = await self.repository.list_items(collection_run_id)
        data = dump_run(run)
        cases = await self.repository.report_cases(list({item.case_id for item in items}))
        case_runs = await self.repository.report_case_runs(
            list({item.case_run_id for item in items if item.case_run_id})
        )
        report_items = []
        for item in items:
            api_case = cases.get(item.case_id)
            case_run = case_runs.get(item.case_run_id) if item.case_run_id else None
            report_item = {
                "itemId": item.item_id,
                "caseId": item.case_id,
                "caseRunId": item.case_run_id or "",
                "caseName": api_case.name if api_case else "",
                "orderNo": item.order_no,
                "status": item.status,
                "continueOnFailure": item.continue_on_failure,
                "errorMessage": item.error_message,
                "startedAt": format_time(item.started_at),
                "finishedAt": format_time(item.finished_at),
                "durationMs": item.duration_ms,
                "request": {},
                "response": {},
                "runtimeVarsJson": "{}",
                "extractResults": [],
                "assertResults": [],
            }
            if case_run:
                report_item["request"] = case_run.request_snapshot_json or {}
                report_item["response"] = case_run.response_snapshot_json or {}
                report_item["runtimeVarsJson"] = json_text(case_run.runtime_vars_json)
                report_item["extractResults"] = case_run.extract_results_json or []
                report_item["assertResults"] = case_run.assert_results_json or []
            report_items.append(report_item)
        data["items"] = report_items
        return data
