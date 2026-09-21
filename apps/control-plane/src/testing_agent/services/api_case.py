from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import (
    ErrApiCaseNameAlreadyUse,
    ErrApiCaseRunEnvironmentMismatch,
    ErrApiCaseRunNotFound,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.schemas.api_case import ApiCaseRequest, ApiCaseResponse
from testing_agent.schemas.api_run import ApiCaseRunResponse, RunApiCaseRequest
from testing_agent.services.api_import_payload import normalize_json_value as normalize_json_value
from testing_agent.services.api_request_render import render_api_case_request
from testing_agent.services.api_run_scope import apply_run_scope, authorize_run
from testing_agent.services.common import list_payload
from testing_agent.services.environment_access import authorized_environment_vars
from testing_agent.services.execution_secrets import protect_run
from testing_agent.services.project_access import ProjectAction, require_project_access


def dump(schema: type[BaseModel], obj: Any) -> dict[str, Any]:
    return schema.model_validate(obj).model_dump(by_alias=True, mode="json")




def api_case_model_data(body: ApiCaseRequest) -> dict[str, Any]:
    data = body.model_dump(by_alias=False)
    data["headers_json"] = normalize_json_value(data.get("headers_json"))
    data["query_json"] = normalize_json_value(data.get("query_json"))
    data["body_json"] = normalize_json_value(data.get("body_json"))
    return data


def apply_api_case_patch(case: ApiCase, body: dict[str, Any]) -> None:
    json_keys = {"headers_json", "query_json", "body_json"}
    allowed = {
        "name",
        "description",
        "enabled",
        "order_no",
        "method",
        "url_template",
        "headers_json",
        "query_json",
        "body_type",
        "body_json",
        "body_text",
        "timeout_ms",
        "continue_on_failure",
    }
    for key, value in body.items():
        snake_key = "".join(
            [f"_{char.lower()}" if char.isupper() else char for char in key]
        ).lstrip("_")
        if snake_key not in allowed:
            continue
        if snake_key in json_keys:
            value = normalize_json_value(value)
        setattr(case, snake_key, value)


class ApiCaseContext:
    def __init__(
        self,
        api_case: ApiCase,
        collection: ApiCollection,
        requirement: Requirement,
        sprint: Sprint,
        project: Project,
    ):
        self.api_case = api_case
        self.collection = collection
        self.requirement = requirement
        self.sprint = sprint
        self.project = project


class ApiCaseService:
    def __init__(self, repository: ApiCaseRepository):
        self.repository = repository

    async def get_accessible_collection(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> ApiCollection:
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
        return collection

    async def get_accessible_context(
        self, user_id: str, case_id: str, *, action: ProjectAction = "read"
    ) -> ApiCaseContext:
        api_case = await self.repository.get_case(case_id)
        if api_case is None:
            raise ErrNotFound
        collection = await self.repository.get_collection(api_case.collection_id)
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
        return ApiCaseContext(api_case, collection, requirement, sprint, project)

    async def create(self, user_id: str, collection_id: str, body: ApiCaseRequest) -> dict:
        await self.get_accessible_collection(user_id, collection_id, action="write")
        exists = await self.repository.get_case_by_collection_and_name(collection_id, body.name)
        if exists is not None:
            raise ErrApiCaseNameAlreadyUse
        api_case = ApiCase(
            case_id=new_id(),
            collection_id=collection_id,
            **api_case_model_data(body),
        )
        self.repository.add(api_case)
        await self.repository.commit()
        await self.repository.refresh(api_case)
        return dump(ApiCaseResponse, api_case)

    async def list_by_collection(self, user_id: str, collection_id: str) -> dict[str, Any]:
        await self.get_accessible_collection(user_id, collection_id, action="read")
        rows = await self.repository.list_cases(collection_id)
        return list_payload([dump(ApiCaseResponse, row) for row in rows])

    async def get(self, user_id: str, case_id: str) -> dict:
        context = await self.get_accessible_context(user_id, case_id, action="read")
        return dump(ApiCaseResponse, context.api_case)

    async def update(self, user_id: str, case_id: str, body: dict[str, Any]) -> dict:
        context = await self.get_accessible_context(user_id, case_id, action="write")
        name = body.get("name")
        if isinstance(name, str) and name != context.api_case.name:
            exists = await self.repository.get_case_by_collection_and_name(
                context.api_case.collection_id, name, case_id
            )
            if exists is not None:
                raise ErrApiCaseNameAlreadyUse
        apply_api_case_patch(context.api_case, body)
        await self.repository.commit()
        await self.repository.refresh(context.api_case)
        return dump(ApiCaseResponse, context.api_case)

    async def delete(self, user_id: str, case_id: str) -> dict:
        context = await self.get_accessible_context(user_id, case_id, action="write")
        await self.repository.hard_delete(context.api_case)
        await self.repository.commit()
        return {}

    async def run(self, user_id: str, case_id: str, body: RunApiCaseRequest) -> dict:
        context = await self.get_accessible_context(user_id, case_id, action="execute")
        environment = await self.repository.get_environment(body.environment_id)
        if environment is None:
            raise ErrNotFound
        if environment.project_id != context.project.project_id:
            raise ErrApiCaseRunEnvironmentMismatch
        env_vars = await authorized_environment_vars(
            self.repository.session, user_id, environment.environment_id
        )
        rendered = render_api_case_request(context.api_case, environment, env_vars)
        run = ApiCaseRun(
            run_id=new_id(),
            case_id=context.api_case.case_id,
            collection_id=context.collection.collection_id,
            environment_id=environment.environment_id,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=RunStatus.PENDING.value,
            request_snapshot_json=rendered.snapshot,
            response_snapshot_json={"statusCode": 0, "headersJson": "{}", "body": ""},
            runtime_vars_json=rendered.runtime_vars,
            extract_results_json=[],
            assert_results_json=[],
            error_message="",
            duration_ms=0,
        )
        protect_run(run, [row.value for row in env_vars if row.is_secret])
        task = WorkerTask(
            domain="api",
            task_id=new_id(),
            task_type="api_case_debug",
            run_id=run.run_id,
            collection_id=context.collection.collection_id,
            case_id=context.api_case.case_id,
            status=RunStatus.PENDING.value,
        )
        self.repository.add_all([run, task])
        await self.repository.commit()
        await self.repository.refresh(run)
        apply_run_scope(run, context)
        return dump(ApiCaseRunResponse, run)

    async def get_run(self, user_id: str, run_id: str) -> dict:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise ErrApiCaseRunNotFound
        await authorize_run(self.repository, user_id, run)
        return dump(ApiCaseRunResponse, run)
