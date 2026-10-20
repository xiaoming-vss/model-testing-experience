from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrFunctionTestCaseImportInvalid,
    ErrNotFound,
    ErrResourceBindingInvalid,
    ErrResourceBindingNotFound,
    ErrZentaoRemoteResourceUnavailable,
    dynamic_error,
)
from testing_agent.domain.function_case_export import FunctionCaseExportSource, case_payload
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.schemas.function_test_case import (
    ImportFunctionCasesToZentaoRequest,
    ImportFunctionSuitesToZentaoRequest,
)
from testing_agent.services.function_case_access import FunctionCaseAccess
from testing_agent.services.import_payload import (
    parse_import_payload,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.zentao_mcp import ZentaoMcpAccess, ZentaoMcpConnection
from testing_agent.services.zentao_mcp_cases import ZentaoMcpCases
from testing_agent.services.zentao_resource import parse_zentao_remote_id, truncate_error


@dataclass(slots=True)
class ZentaoFunctionCaseImportTarget:
    connection: ZentaoMcpConnection
    product_id: int
    module_id: int
    remote_project_id: int
    remote_execution_id: int
    remote_story_id: int


def item_value(item: Any, key: str, *, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class FunctionCaseExporter:
    def __init__(
        self,
        repository: FunctionTestCaseRepository,
        integration_connection_service: IntegrationConnectionService | None = None,
        zentao_resource_client: ZentaoMcpCases | None = None,
        *,
        zentao_access: ZentaoMcpAccess | None = None,
    ) -> None:
        self.repository = repository
        self.access = FunctionCaseAccess(repository)
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client
        self.zentao_access = zentao_access

    async def import_to_zentao(self, user_id: str, suite_id: str, payload: Any) -> dict:
        if isinstance(payload, ImportFunctionCasesToZentaoRequest):
            request = payload
        else:
            try:
                request = ImportFunctionCasesToZentaoRequest.model_validate(
                    parse_import_payload(payload)
                )
            except ValidationError as exc:
                raise ErrBadRequest() from exc

        suite, requirement, sprint, project = await self.access.get_accessible_suite_context(
            user_id, suite_id, action="execute"
        )
        cases = await self.resolve_cases_for_zentao_import(suite.suite_id, request.case_ids)
        if not cases:
            raise dynamic_error(ErrFunctionTestCaseImportInvalid, "测试集下没有可导入用例")
        target = await self.resolve_zentao_import_target(
            user_id,
            requirement,
            sprint,
            project,
            request.product_id,
            request.module_id,
            request.connection_id,
        )
        return await self.import_suite_cases_to_zentao(suite.suite_id, cases, target)

    async def import_requirement_to_zentao(
        self,
        user_id: str,
        requirement_id: str,
        payload: Any,
    ) -> dict:
        if isinstance(payload, ImportFunctionSuitesToZentaoRequest):
            request = payload
        else:
            try:
                request = ImportFunctionSuitesToZentaoRequest.model_validate(payload)
            except ValidationError as exc:
                raise ErrBadRequest() from exc

        requirement, sprint, project = await self.access.get_accessible_requirement_context(
            user_id, requirement_id, action="execute"
        )
        suites = await self.resolve_suites_for_zentao_import(requirement_id, request.suite_ids)
        target = await self.resolve_zentao_import_target(
            user_id,
            requirement,
            sprint,
            project,
            request.product_id,
            request.module_id,
            request.connection_id,
        )

        items = []
        imported_case_count = 0
        succeeded_suite_count = 0
        uncertain = False
        for suite in suites:
            if uncertain:
                items.append(
                    {
                        "suiteId": suite.suite_id,
                        "status": "failed",
                        "importedCaseCount": 0,
                        "errorMessage": "前序测试集写入结果待核对，本测试集未推送",
                    }
                )
                continue
            try:
                cases = await self.repository.list_by_suite(suite.suite_id)
                result = await self.import_suite_cases_to_zentao(suite.suite_id, cases, target)
            except AppError as exc:
                items.append(
                    {
                        "suiteId": suite.suite_id,
                        "status": "failed",
                        "importedCaseCount": 0,
                        "errorCode": exc.code,
                        "errorMessage": exc.message,
                    }
                )
                continue
            uncertain = any(item["status"] == "uncertain" for item in result["items"])
            succeeded_suite_count += int(result.get("status", "success") == "success")
            imported_case_count += result["importedCaseCount"]
            items.append(
                {
                    "suiteId": suite.suite_id,
                    "status": "success"
                    if result.get("status", "success") == "success"
                    else "failed",
                    "errorMessage": next(
                        (
                            item.get("errorMessage")
                            for item in result["items"]
                            if item.get("errorMessage")
                        ),
                        None,
                    ),
                    "items": result["items"],
                    "importedCaseCount": result["importedCaseCount"],
                }
            )

        total_suite_count = len(suites)
        failed_suite_count = total_suite_count - succeeded_suite_count
        if failed_suite_count == 0:
            status = "success"
        elif imported_case_count == 0:
            status = "failed"
        else:
            status = "partial_failure"
        return {
            "requirementId": requirement_id,
            "status": status,
            "totalSuiteCount": total_suite_count,
            "succeededSuiteCount": succeeded_suite_count,
            "failedSuiteCount": failed_suite_count,
            "importedCaseCount": imported_case_count,
            "items": items,
        }

    async def resolve_zentao_import_target(
        self,
        user_id: str,
        requirement: Requirement,
        sprint: Sprint,
        project: Project,
        product_id: int,
        module_id: int,
        connection_id: str = "",
    ) -> ZentaoFunctionCaseImportTarget:

        project_binding = await self.get_required_binding(
            "project",
            project.project_id,
            "请先绑定所属项目",
        )
        sprint_binding = await self.get_required_binding(
            "sprint",
            sprint.sprint_id,
            "请先绑定所属迭代",
        )
        requirement_binding = await self.get_required_binding(
            "requirement",
            requirement.requirement_id,
            "请先绑定所属需求",
        )
        self.validate_zentao_binding(project_binding, "project")
        self.validate_zentao_binding(sprint_binding, "execution")
        self.validate_zentao_binding(requirement_binding, "story")
        if (
            project_binding.instance_key != sprint_binding.instance_key
            or project_binding.instance_key != requirement_binding.instance_key
        ):
            raise dynamic_error(
                ErrResourceBindingInvalid,
                "项目、迭代和需求必须绑定到同一禅道实例",
            )
        if sprint_binding.remote_parent_id != project_binding.remote_resource_id:
            raise ErrResourceBindingInvalid()
        if (
            requirement_binding.remote_parent_id
            and requirement_binding.remote_parent_id != sprint_binding.remote_resource_id
        ):
            raise dynamic_error(
                ErrResourceBindingInvalid,
                "需求绑定的禅道需求不属于所属迭代绑定的禅道执行",
            )

        try:
            remote_project_id = parse_zentao_remote_id(project_binding.remote_resource_id)
            remote_execution_id = parse_zentao_remote_id(sprint_binding.remote_resource_id)
            remote_story_id = parse_zentao_remote_id(requirement_binding.remote_resource_id)
        except ValueError as exc:
            raise dynamic_error(ErrResourceBindingInvalid, str(exc)) from exc

        if self.integration_connection_service is None or self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        access = self.zentao_access or ZentaoMcpAccess(self.integration_connection_service)
        connection = await access.resolve(user_id, project.project_id, project_binding.instance_url)
        await self.zentao_resource_client.validate_target(
            connection, remote_project_id, remote_execution_id, remote_story_id, product_id
        )
        return ZentaoFunctionCaseImportTarget(
            connection=connection,
            product_id=product_id,
            module_id=module_id,
            remote_project_id=remote_project_id,
            remote_execution_id=remote_execution_id,
            remote_story_id=remote_story_id,
        )

    async def import_suite_cases_to_zentao(
        self,
        suite_id: str,
        cases: list[FunctionTestCase],
        target: ZentaoFunctionCaseImportTarget,
    ) -> dict:
        if not cases:
            raise dynamic_error(ErrFunctionTestCaseImportInvalid, "测试集下没有可导入用例")
        create_body: dict[str, Any] = {
            "productID": target.product_id,
            "project": target.remote_project_id,
            "execution": target.remote_execution_id,
            "cases": [],
        }
        create_body["cases"] = [
            case_payload(
                FunctionCaseExportSource(
                    case_id=case.case_id,
                    title=case.title,
                    preconditions=case.preconditions,
                    steps=case.steps,
                    expected_results=case.expected_results,
                    priority=case.priority,
                    content_json=getattr(case, "content_json", None),
                ),
                module_id=target.module_id,
                story_id=target.remote_story_id,
            )
            for case in cases
        ]

        if self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable()
        try:
            result = await self.zentao_resource_client.create_test_cases(
                target.connection, create_body
            )
        except Exception as exc:
            raise dynamic_error(
                ErrZentaoRemoteResourceUnavailable,
                truncate_error(str(exc)),
            ) from exc
        remote_items = result.get("items") or []
        if len(remote_items) < len(cases):
            raise dynamic_error(ErrZentaoRemoteResourceUnavailable, "禅道测试用例创建结果数量不足")

        items = []
        for index, case in enumerate(cases):
            remote = remote_items[index]
            items.append(
                {
                    "caseId": case.case_id,
                    "remoteCaseId": int(item_value(remote, "id", default=0)),
                    "status": str(item_value(remote, "status", default="failed") or "failed"),
                    **(
                        {"errorMessage": remote["errorMessage"]}
                        if remote.get("errorMessage")
                        else {}
                    ),
                }
            )
        return {
            "suiteId": suite_id,
            "productId": target.product_id,
            "remoteProjectId": target.remote_project_id,
            "remoteExecutionId": target.remote_execution_id,
            "importedCaseCount": sum(item["status"] == "success" for item in items),
            "status": "success"
            if all(item["status"] == "success" for item in items)
            else (
                "partial_failure"
                if any(item["status"] == "success" for item in items)
                else "failed"
            ),
            "items": items,
        }

    async def resolve_suites_for_zentao_import(
        self,
        requirement_id: str,
        suite_ids: list[str],
    ) -> list[FunctionTestSuite]:
        if not suite_ids or len(set(suite_ids)) != len(suite_ids):
            raise ErrBadRequest()
        rows = await self.repository.list_suites_by_ids(suite_ids)
        suites_by_id = {suite.suite_id: suite for suite in rows}
        for suite_id in suite_ids:
            suite = suites_by_id.get(suite_id)
            if suite is None:
                raise ErrNotFound()
            if suite.requirement_id != requirement_id:
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"测试集不属于当前需求: {suite_id}",
                )
        return [suites_by_id[suite_id] for suite_id in suite_ids]

    async def resolve_cases_for_zentao_import(
        self,
        suite_id: str,
        case_ids: list[str],
    ) -> list[FunctionTestCase]:
        if not case_ids:
            return await self.repository.list_by_suite(suite_id)
        result = []
        seen = set()
        for index, case_id in enumerate(case_ids):
            normalized = str(case_id or "").strip()
            if not normalized:
                raise dynamic_error(ErrFunctionTestCaseImportInvalid, f"caseIds[{index}] 不能为空")
            if normalized in seen:
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"caseIds[{index}] 重复: {normalized}",
                )
            seen.add(normalized)
            case = await self.repository.get_case(normalized)
            if case is None:
                raise ErrNotFound()
            if case.suite_id != suite_id:
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"用例不属于当前测试集: {normalized}",
                )
            result.append(case)
        return result

    async def get_required_binding(
        self,
        resource_type: str,
        resource_id: str,
        message: str,
    ) -> ResourceBinding:
        binding = await self.repository.get_active_binding(resource_type, resource_id)
        if binding is None:
            raise dynamic_error(ErrResourceBindingNotFound, message)
        return binding

    @staticmethod
    def validate_zentao_binding(binding: ResourceBinding, remote_resource_type: str) -> None:
        aliases = {
            "execution": {"execution", "sprint"},
            "story": {"story", "requirement"},
        }
        allowed_types = aliases.get(remote_resource_type, {remote_resource_type})
        if binding.provider != "zentao" or binding.remote_resource_type not in allowed_types:
            raise dynamic_error(ErrResourceBindingInvalid, "资源绑定不是有效的禅道绑定")
