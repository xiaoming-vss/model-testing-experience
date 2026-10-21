from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from testing_agent.core.config import Settings, get_settings
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
from testing_agent.domain.integration_execution import digest
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.schemas.function_test_case import (
    CasePushReconcileRequest,
    ImportFunctionCasesToZentaoRequest,
    ImportFunctionSuitesToZentaoRequest,
)
from testing_agent.services.function_case_access import FunctionCaseAccess
from testing_agent.services.function_case_push_flow import (
    CasePushScope,
    FunctionCasePushFlow,
    export_payload,
)
from testing_agent.services.import_payload import (
    parse_import_payload,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.zentao_case_gateway import ZentaoCaseGateway, open_case_gateway
from testing_agent.services.zentao_mcp import ZentaoMcpAccess, ZentaoMcpConnection
from testing_agent.services.zentao_mcp_cases import ZentaoMcpCases
from testing_agent.services.zentao_resource import parse_zentao_remote_id


@dataclass(slots=True)
class ZentaoFunctionCaseImportTarget:
    connection: ZentaoMcpConnection
    product_id: int
    module_id: int
    remote_project_id: int
    remote_execution_id: int
    remote_story_id: int


class FunctionCaseExporter:
    def __init__(
        self,
        repository: FunctionTestCaseRepository,
        integration_connection_service: IntegrationConnectionService | None = None,
        zentao_resource_client: ZentaoMcpCases | None = None,
        *,
        zentao_access: ZentaoMcpAccess | None = None,
        settings: Settings | None = None,
        push_flow: FunctionCasePushFlow | None = None,
        gateway_factory=open_case_gateway,
    ) -> None:
        self.repository = repository
        self.access = FunctionCaseAccess(repository)
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client
        self.zentao_access = zentao_access
        self.settings = settings or get_settings()
        self.push_flow = push_flow
        self.gateway_factory = gateway_factory

    def workflow(self) -> FunctionCasePushFlow:
        if self.push_flow is None:
            if self.integration_connection_service is None:
                raise ErrZentaoRemoteResourceUnavailable()
            self.push_flow = FunctionCasePushFlow(
                self.repository,
                self.integration_connection_service.credentials,
                self.settings,
            )
        return self.push_flow

    @staticmethod
    def scope(
        suite_id: str,
        requirement_id: str,
        sprint_id: str,
        project_id: str,
        target: ZentaoFunctionCaseImportTarget,
    ) -> CasePushScope:
        return CasePushScope(
            project_id,
            suite_id,
            requirement_id,
            sprint_id,
            target.connection,
            {
                "productID": target.product_id,
                "project": target.remote_project_id,
                "execution": target.remote_execution_id,
                "story": target.remote_story_id,
                "module": target.module_id,
            },
        )

    async def prepare_suite(
        self,
        user_id: str,
        suite_id: str,
        request: ImportFunctionCasesToZentaoRequest,
        *,
        preview: bool = False,
    ) -> tuple[CasePushScope, dict[str, dict[str, Any]]]:
        suite, requirement, sprint, project = await self.access.get_accessible_suite_context(
            user_id, suite_id, action="execute"
        )
        cases = await self.resolve_cases_for_zentao_import(suite.suite_id, request.case_ids)
        fingerprint = digest(
            {
                "suiteId": suite_id,
                "request": request.model_dump(mode="json", exclude={"request_id"}),
            }
        )
        selected = (
            await self.workflow().frozen_selection(user_id, request.request_id, fingerprint)
            if not preview
            else None
        )
        if selected is not None:
            cases = [case for case in cases if case.case_id in selected]
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
        scope = self.scope(
            suite_id, requirement.requirement_id, sprint.sprint_id, project.project_id, target
        )
        payloads = {
            case.case_id: ({"title": case.title} if preview else export_payload(case, scope.target))
            for case in cases
        }
        return scope, payloads

    async def import_to_zentao(self, user_id: str, suite_id: str, payload: Any) -> dict:
        try:
            request = (
                ImportFunctionCasesToZentaoRequest.model_validate(parse_import_payload(payload))
                if not isinstance(payload, ImportFunctionCasesToZentaoRequest)
                else payload
            )
        except ValidationError as exc:
            raise ErrBadRequest() from exc
        scope, payloads = await self.prepare_suite(user_id, suite_id, request)
        fingerprint = digest(
            {
                "suiteId": suite_id,
                "request": request.model_dump(mode="json", exclude={"request_id"}),
            }
        )
        manifest = await self.workflow().admit(
            user_id,
            scope,
            request.request_id,
            fingerprint,
            {
                case_id: {"suiteId": suite_id, "digest": digest(body), "order": str(index)}
                for index, (case_id, body) in enumerate(payloads.items())
            },
        )
        async with self.gateway_factory(scope.connection) as gateway:
            return await self.push_suite(
                user_id, scope, payloads, request, gateway, manifest, fingerprint
            )

    async def preview_suite(
        self, user_id: str, suite_id: str, request: ImportFunctionCasesToZentaoRequest
    ) -> dict:
        scope, payloads = await self.prepare_suite(user_id, suite_id, request, preview=True)
        await self.repository.session.rollback()
        async with self.gateway_factory(scope.connection) as gateway:
            return await self.workflow().preview(user_id, scope, gateway, payloads)

    async def push_suite(
        self,
        user_id: str,
        scope: CasePushScope,
        payloads: dict[str, dict[str, Any]],
        request: ImportFunctionCasesToZentaoRequest | ImportFunctionSuitesToZentaoRequest,
        gateway: ZentaoCaseGateway,
        manifest: dict[str, dict[str, str]],
        fingerprint: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        stopped = False
        selected = sorted(
            (key for key, entry in manifest.items() if entry["suiteId"] == scope.suite_id),
            key=lambda key: int(manifest[key]["order"]),
        )
        for case_id in selected:
            if stopped:
                items.append(
                    {
                        "caseId": case_id,
                        "remoteCaseId": 0,
                        "status": "skipped",
                        "errorMessage": "前序用例未成功，未继续推送",
                    }
                )
                continue
            try:
                if case_id not in payloads:
                    raise ErrNotFound()
                payload = payloads[case_id]
                result = await self.workflow().push_one(
                    user_id,
                    scope,
                    gateway,
                    case_id=case_id,
                    payload=payload,
                    request_id=request.request_id,
                    request_fingerprint=fingerprint,
                    choice=request.choices.get(case_id),
                    restore_confirmed=request.restore_confirmed,
                    expected_payload_digest=manifest[case_id]["digest"],
                )
            except AppError as exc:
                await self.repository.session.rollback()
                result = {
                    "caseId": case_id,
                    "remoteCaseId": 0,
                    "status": "failed",
                    "errorMessage": exc.message,
                    "errorCode": exc.code,
                }
            items.append(result)
            stopped = result["status"] != "success"
        count = sum(item["status"] == "success" for item in items)
        return {
            "suiteId": scope.suite_id,
            "productId": scope.target["productID"],
            "remoteProjectId": scope.target["project"],
            "remoteExecutionId": scope.target["execution"],
            "importedCaseCount": count,
            "status": "success"
            if count == len(items)
            else "partial_failure"
            if count
            else "failed",
            "items": items,
        }

    async def import_requirement_to_zentao(
        self, user_id: str, requirement_id: str, payload: Any
    ) -> dict:
        try:
            request = (
                payload
                if isinstance(payload, ImportFunctionSuitesToZentaoRequest)
                else ImportFunctionSuitesToZentaoRequest.model_validate(payload)
            )
        except ValidationError as exc:
            raise ErrBadRequest() from exc
        requirement, sprint, project = await self.access.get_accessible_requirement_context(
            user_id, requirement_id, action="execute"
        )
        suites = await self.resolve_suites_for_zentao_import(requirement_id, request.suite_ids)
        suite_ids = [suite.suite_id for suite in suites]
        sprint_id, project_id = sprint.sprint_id, project.project_id
        target = await self.resolve_zentao_import_target(
            user_id,
            requirement,
            sprint,
            project,
            request.product_id,
            request.module_id,
            request.connection_id,
        )
        fingerprint = digest(
            {
                "requirementId": requirement_id,
                "request": request.model_dump(mode="json", exclude={"request_id"}),
            }
        )
        selected = await self.workflow().frozen_selection(user_id, request.request_id, fingerprint)
        batches: dict[str, dict[str, dict[str, Any]]] = {}
        entries: dict[str, dict[str, str]] = {}
        for suite_id in suite_ids:
            scope = self.scope(suite_id, requirement_id, sprint_id, project_id, target)
            cases = await self.repository.list_by_suite(suite_id)
            batches[suite_id] = {
                case.case_id: export_payload(case, scope.target)
                for case in cases
                if selected is None or case.case_id in selected
            }
            for case_id, body in batches[suite_id].items():
                entries[case_id] = {
                    "suiteId": suite_id,
                    "digest": digest(body),
                    "order": str(len(entries)),
                }
        fingerprint = digest(
            {
                "requirementId": requirement_id,
                "request": request.model_dump(mode="json", exclude={"request_id"}),
            }
        )
        manifest = await self.workflow().admit(
            user_id,
            self.scope(suite_ids[0], requirement_id, sprint_id, project_id, target),
            request.request_id,
            fingerprint,
            entries,
        )
        items: list[dict[str, Any]] = []
        uncertain = False
        async with self.gateway_factory(target.connection) as gateway:
            for suite_id in suite_ids:
                if uncertain:
                    items.append(
                        {
                            "suiteId": suite_id,
                            "status": "failed",
                            "importedCaseCount": 0,
                            "errorMessage": "前序测试集写入结果待核对，本测试集未推送",
                        }
                    )
                    continue
                try:
                    payloads = batches[suite_id]
                    if not any(entry["suiteId"] == suite_id for entry in manifest.values()):
                        raise dynamic_error(
                            ErrFunctionTestCaseImportInvalid, "测试集下没有可导入用例"
                        )
                    scope = self.scope(suite_id, requirement_id, sprint_id, project_id, target)
                    result = await self.push_suite(
                        user_id, scope, payloads, request, gateway, manifest, fingerprint
                    )
                    if result["importedCaseCount"] == 0 and result["items"][0].get("errorCode"):
                        error = result["items"][0]
                        items.append(
                            {
                                "suiteId": suite_id,
                                "status": "failed",
                                "importedCaseCount": 0,
                                "errorCode": error["errorCode"],
                                "errorMessage": error["errorMessage"],
                            }
                        )
                        continue
                    uncertain = any(
                        item["status"] in {"uncertain", "pending"} for item in result["items"]
                    )
                    items.append(
                        {
                            "suiteId": suite_id,
                            "status": "success" if result["status"] == "success" else "failed",
                            "importedCaseCount": result["importedCaseCount"],
                            "items": result["items"],
                            "errorMessage": next(
                                (
                                    item.get("errorMessage")
                                    for item in result["items"]
                                    if item.get("errorMessage")
                                ),
                                None,
                            ),
                        }
                    )
                except AppError as exc:
                    await self.repository.session.rollback()
                    items.append(
                        {
                            "suiteId": suite_id,
                            "status": "failed",
                            "importedCaseCount": 0,
                            "errorCode": exc.code,
                            "errorMessage": exc.message,
                        }
                    )
        count = sum(item["importedCaseCount"] for item in items)
        succeeded = sum(item["status"] == "success" for item in items)
        return {
            "requirementId": requirement_id,
            "status": "success"
            if succeeded == len(items)
            else "partial_failure"
            if count
            else "failed",
            "totalSuiteCount": len(items),
            "succeededSuiteCount": succeeded,
            "failedSuiteCount": len(items) - succeeded,
            "importedCaseCount": count,
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

    async def preview_requirement(
        self,
        actor: str,
        requirement_id: str,
        request: ImportFunctionSuitesToZentaoRequest,
    ) -> dict[str, Any]:
        requirement, sprint, project = await self.access.get_accessible_requirement_context(
            actor, requirement_id, action="execute"
        )
        suites = await self.resolve_suites_for_zentao_import(requirement_id, request.suite_ids)
        suite_ids = [suite.suite_id for suite in suites]
        sprint_id, project_id = sprint.sprint_id, project.project_id
        target = await self.resolve_zentao_import_target(
            actor,
            requirement,
            sprint,
            project,
            request.product_id,
            request.module_id,
            request.connection_id,
        )
        owner = project.user_id == actor
        await self.repository.session.rollback()
        result: list[dict[str, Any]] = []
        restore_required = False
        async with self.gateway_factory(target.connection) as gateway:
            for suite_id in suite_ids:
                scope = self.scope(suite_id, requirement_id, sprint_id, project_id, target)
                cases = await self.repository.list_by_suite(suite_id)
                payloads = {case.case_id: {"title": case.title} for case in cases}
                preview = await self.workflow().preview(actor, scope, gateway, payloads)
                result.extend(preview["items"])
                restore_required = restore_required or preview["restoreRequired"]
        return {"items": result, "restoreRequired": restore_required, "canConfirmNotApplied": owner}

    async def operation_status(self, actor: str, operation_id: str) -> dict[str, Any]:
        return await self.workflow().status(actor, operation_id)

    async def reconcile_operation(
        self,
        actor: str,
        suite_id: str,
        operation_id: str,
        body: CasePushReconcileRequest,
    ) -> dict[str, Any]:
        await self.access.get_accessible_suite(actor, suite_id, action="execute")
        operation = await self.workflow().journal_repository.operation(operation_id, lock=False)
        if operation is None:
            raise ErrNotFound()
        case = await self.repository.get_case(operation.case_id)
        if case is None or case.suite_id != suite_id:
            raise ErrNotFound()
        request = ImportFunctionCasesToZentaoRequest(
            productId=operation.target_json["productID"],
            module_id=operation.payload_json["module"],
            case_ids=[operation.case_id],
        )
        scope, _ = await self.prepare_suite(actor, suite_id, request, preview=True)
        await self.repository.session.rollback()
        async with self.gateway_factory(scope.connection) as gateway:
            if body.resolution == "not_applied":
                if not body.confirmed_not_applied:
                    raise AppError(400, "必须明确确认人工核对结论", 400)
                return await self.workflow().confirm_not_applied(
                    actor, scope, gateway, operation_id, body.reason
                )
            if body.remote_case_id is None:
                raise ErrBadRequest()
            return await self.workflow().reconcile(
                actor, scope, gateway, operation_id, body.remote_case_id
            )
