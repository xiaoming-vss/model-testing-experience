from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import (
    ErrApiCaseRunEnvironmentMismatch,
    ErrNotFound,
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
from testing_agent.services.api_run_scope import apply_run_scope, authorize_run
from testing_agent.services.common import dump, list_payload
from testing_agent.services.environment_access import authorized_environment_vars
from testing_agent.services.execution_secrets import protect_run
from testing_agent.services.project_access import ProjectAction, require_project_access


class ApiCollectionRunContext:
    def __init__(
        self,
        collection: ApiCollection,
        requirement: Requirement,
        sprint: Sprint,
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

    async def get_accessible_context(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> ApiCollectionRunContext:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound
        requirement = await self.repository.get_requirement(collection.requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return ApiCollectionRunContext(collection, requirement, sprint, project)

    async def ensure_owned_run(self, user_id: str, collection_run_id: str) -> ApiCollectionRun:
        run = await self.repository.get_run(collection_run_id)
        if run is None:
            raise ErrNotFound
        await authorize_run(self.repository, user_id, run)
        return run

    async def run(self, user_id: str, collection_id: str, body: RunApiCollectionRequest) -> dict:
        context = await self.get_accessible_context(user_id, collection_id, action="execute")
        environment = await self.repository.get_environment(body.environment_id)
        if environment is None:
            raise ErrNotFound
        if environment.project_id != context.project.project_id:
            raise ErrApiCaseRunEnvironmentMismatch
        cases = await self.repository.list_cases(collection_id)
        env_vars = await authorized_environment_vars(
            self.repository.session, user_id, environment.environment_id
        )
        run = ApiCollectionRun(
            collection_run_id=new_id(),
            collection_id=collection_id,
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
            collection_run_id=run.collection_run_id,
            collection_id=collection_id,
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
        await self.repository.refresh(run)
        apply_run_scope(run, context)
        return dump_run(run)

    async def list(self, user_id: str, collection_id: str) -> dict[str, Any]:
        context = await self.get_accessible_context(user_id, collection_id, action="read")
        rows = await self.repository.list_runs(collection_id)
        for row in rows:
            apply_run_scope(row, context)
        return list_payload([dump_run(row) for row in rows])

    async def get(self, user_id: str, collection_run_id: str) -> dict:
        return dump_run(await self.ensure_owned_run(user_id, collection_run_id))

    async def report(self, user_id: str, collection_run_id: str) -> dict:
        run = await self.ensure_owned_run(user_id, collection_run_id)
        items = await self.repository.list_items(collection_run_id)
        data = dump_run(run)
        report_items = []
        for item in items:
            api_case = await self.repository.get_case(item.case_id)
            case_run = (
                await self.repository.get_case_run(item.case_run_id) if item.case_run_id else None
            )
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
