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
from testing_agent.core.sid import new_id
from testing_agent.domain.function_case_content import CaseContent, set_legacy_content
from testing_agent.domain.function_case_query import FunctionCaseQuery
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.schemas.function_test_case import (
    FunctionCaseLibraryItem,
    FunctionCaseRequest,
    FunctionCaseResponse,
    ImportFunctionCasesToZentaoRequest,
    ImportFunctionSuitesToZentaoRequest,
)
from testing_agent.services.api_collection import (
    import_items,
    parse_import_payload,
    read_import_payload,
)
from testing_agent.services.common import apply_patch, dump, list_payload, paged_payload
from testing_agent.services.project_access import (
    ProjectAction,
    require_project_access,
    require_project_id,
)
from testing_agent.services.zentao_resource import parse_zentao_remote_id, truncate_error


@dataclass(slots=True)
class ZentaoFunctionCaseImportTarget:
    connection: Any
    product_id: int
    module_id: int
    remote_project_id: int
    remote_execution_id: int
    remote_story_id: int


class FunctionTestCaseService:
    def __init__(
        self,
        repository: FunctionTestCaseRepository,
        integration_connection_service: Any | None = None,
        zentao_resource_client: Any | None = None,
    ):
        self.repository = repository
        self.integration_connection_service = integration_connection_service
        self.zentao_resource_client = zentao_resource_client

    async def get_accessible_suite(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> FunctionTestSuite:
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
        return suite

    async def get_accessible_entity(
        self, user_id: str, case_id: str, *, action: ProjectAction = "read"
    ) -> FunctionTestCase:
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ErrNotFound
        await self.get_accessible_suite(user_id, case.suite_id, action=action)
        return case

    async def create(self, user_id: str, suite_id: str, body: FunctionCaseRequest) -> dict:
        await self.get_accessible_suite(user_id, suite_id, action="write")
        case = FunctionTestCase(
            case_id=new_id(),
            suite_id=suite_id,
            **body.model_dump(by_alias=False),
        )
        self.repository.add(case)
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(FunctionCaseResponse, case)

    async def import_cases(self, user_id: str, suite_id: str, payload: Any, file: Any) -> dict:
        await self.get_accessible_suite(user_id, suite_id, action="write")
        parsed = await read_import_payload(payload, file)
        created = 0
        for index, item in enumerate(import_items(parsed, "cases", "functionCases", "testcases")):
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if content is not None:
                try:
                    content = CaseContent.model_validate(content).model_dump()
                except ValidationError as exc:
                    raise dynamic_error(
                        ErrFunctionTestCaseImportInvalid,
                        f"第 {index + 1} 条用例正文格式不正确",
                    ) from exc
            self.repository.add(
                FunctionTestCase(
                    case_id=new_id(),
                    suite_id=suite_id,
                    content=content,
                    module=str(item.get("module") or ""),
                    title=str(
                        item.get("title") or item.get("name") or f"Function Case {index + 1}"
                    ),
                    preconditions=str(item.get("preconditions") or item.get("precondition") or ""),
                    steps=str(item.get("steps") or ""),
                    expected_results=str(
                        item.get("expectedResults") or item.get("expected_results") or ""
                    ),
                    priority=str(item.get("priority") or ""),
                    case_type=str(item.get("caseType") or item.get("case_type") or ""),
                    order_no=int(item.get("orderNo", item.get("order_no", index)) or 0),
                )
            )
            created += 1
        await self.repository.commit()
        return {"imported": created}

    async def import_to_zentao(self, user_id: str, suite_id: str, payload: Any) -> dict:
        if isinstance(payload, ImportFunctionCasesToZentaoRequest):
            request = payload
        else:
            try:
                request = ImportFunctionCasesToZentaoRequest.model_validate(
                    parse_import_payload(payload)
                )
            except ValidationError as exc:
                raise ErrBadRequest from exc

        suite, requirement, sprint, project = await self.get_accessible_suite_context(
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
                raise ErrBadRequest from exc

        requirement, sprint, project = await self.get_accessible_requirement_context(
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
        for suite in suites:
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
            succeeded_suite_count += 1
            imported_case_count += result["importedCaseCount"]
            items.append(
                {
                    "suiteId": suite.suite_id,
                    "status": "success",
                    "importedCaseCount": result["importedCaseCount"],
                }
            )

        total_suite_count = len(suites)
        failed_suite_count = total_suite_count - succeeded_suite_count
        if failed_suite_count == 0:
            status = "success"
        elif succeeded_suite_count == 0:
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
        requirement: Any,
        sprint: Any,
        project: Any,
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
            raise ErrResourceBindingInvalid
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
            raise ErrZentaoRemoteResourceUnavailable
        selected = await self.integration_connection_service.resolve_personal_connection(
            user_id, "zentao", project.project_id, project_binding.instance_url, connection_id
        )
        connection = await self.integration_connection_service.resolve_zentao_access(
            user_id, selected.connection_id, project.project_id
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
        for case in cases:
            content = getattr(case, "content_json", None)
            if content is not None:
                pairs = CaseContent.model_validate(content).steps
                steps = [step.action for step in pairs]
                expects = [step.expected for step in pairs]
            else:
                steps = split_zentao_lines(case.steps)
                expects = split_zentao_lines(case.expected_results)
            if not steps or any(not step.strip() for step in steps):
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"用例[{case.case_id}]测试步骤不能为空",
                )
            if not expects or any(not expected.strip() for expected in expects):
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"用例[{case.case_id}]预期结果不能为空",
                )
            steps, expects = normalize_zentao_steps_and_expects(steps, expects)
            create_body["cases"].append(
                {
                    "title": case.title.strip(),
                    "module": target.module_id,
                    "story": target.remote_story_id,
                    "pri": zentao_priority(case.priority),
                    "precondition": case.preconditions.strip(),
                    "steps": steps,
                    "expects": expects,
                }
            )

        if self.zentao_resource_client is None:
            raise ErrZentaoRemoteResourceUnavailable
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
                    "status": str(item_value(remote, "status", default="success") or "success"),
                }
            )
        return {
            "suiteId": suite_id,
            "productId": target.product_id,
            "remoteProjectId": target.remote_project_id,
            "remoteExecutionId": target.remote_execution_id,
            "importedCaseCount": len(items),
            "items": items,
        }

    async def get_accessible_requirement_context(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> tuple[Any, Any, Any]:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)
        return requirement, sprint, project

    async def resolve_suites_for_zentao_import(
        self,
        requirement_id: str,
        suite_ids: list[str],
    ) -> list[FunctionTestSuite]:
        if not suite_ids or len(set(suite_ids)) != len(suite_ids):
            raise ErrBadRequest
        rows = await self.repository.list_suites_by_ids(suite_ids)
        suites_by_id = {suite.suite_id: suite for suite in rows}
        for suite_id in suite_ids:
            suite = suites_by_id.get(suite_id)
            if suite is None:
                raise ErrNotFound
            if suite.requirement_id != requirement_id:
                raise dynamic_error(
                    ErrFunctionTestCaseImportInvalid,
                    f"测试集不属于当前需求: {suite_id}",
                )
        return [suites_by_id[suite_id] for suite_id in suite_ids]

    async def get_accessible_suite_context(
        self, user_id: str, suite_id: str, *, action: ProjectAction = "read"
    ) -> tuple[Any, Any, Any, Any]:
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
        return suite, requirement, sprint, project

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
                raise ErrNotFound
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

    async def list(self, user_id: str, suite_id: str) -> dict[str, Any]:
        await self.get_accessible_suite(user_id, suite_id, action="read")
        rows = await self.repository.list_by_suite(suite_id)
        return list_payload([dump(FunctionCaseResponse, row) for row in rows])

    async def list_project_cases(self, user_id: str, query: FunctionCaseQuery) -> dict[str, Any]:
        """项目范围内的用例检索：跨迭代 / 需求 / 测试集筛选并分页。"""
        await require_project_id(self.repository.session, user_id, query.project_id, action="read")
        cases, total = await self.repository.list_by_project(query)
        return paged_payload([dump(FunctionCaseLibraryItem, case) for case in cases], total)

    async def get(self, user_id: str, case_id: str) -> dict:
        return dump(
            FunctionCaseResponse, await self.get_accessible_entity(user_id, case_id, action="read")
        )

    async def update(self, user_id: str, case_id: str, body: dict[str, Any]) -> dict:
        case = await self.get_accessible_entity(user_id, case_id, action="write")
        body = dict(body)
        structured = body.pop("content", None)
        legacy = {}
        for key, alias in (
            ("preconditions", "preconditions"),
            ("steps", "steps"),
            ("expected_results", "expectedResults"),
        ):
            if key in body:
                legacy[key] = body.pop(key)
            elif alias in body:
                legacy[key] = body.pop(alias)
        if structured is not None:
            case.content_json = CaseContent.model_validate(structured).model_dump()
        elif legacy:
            set_legacy_content(
                case,
                **{
                    key: legacy.get(key, getattr(case, key))
                    for key in ("preconditions", "steps", "expected_results")
                },
            )
        apply_patch(
            case,
            body,
            {
                "module",
                "title",
                "preconditions",
                "steps",
                "expected_results",
                "priority",
                "case_type",
                "order_no",
            },
        )
        await self.repository.commit()
        await self.repository.refresh(case)
        return dump(FunctionCaseResponse, case)

    async def batch_delete(self, user_id: str, suite_id: str, case_ids: list[str]) -> dict:
        await self.get_accessible_suite(user_id, suite_id, action="write")
        cases = []
        for case_id in case_ids:
            case = await self.repository.get_case(case_id)
            if case is None or case.suite_id != suite_id:
                raise ErrNotFound
            cases.append(case)
        try:
            for case in cases:
                await self.repository.hard_delete(case)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return {"deletedIds": case_ids, "deletedCount": len(case_ids)}

    async def delete(self, user_id: str, case_id: str) -> dict:
        case = await self.get_accessible_entity(user_id, case_id, action="write")
        await self.repository.hard_delete(case)
        await self.repository.commit()
        return {}


def split_zentao_lines(value: str) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in text.split("\n") if part.strip()]


def normalize_zentao_steps_and_expects(
    steps: list[str],
    expects: list[str],
) -> tuple[list[str], list[str]]:
    if len(steps) == len(expects):
        return steps, expects
    target = max(len(steps), len(expects))
    return (
        steps + [" "] * (target - len(steps)),
        expects + [" "] * (target - len(expects)),
    )


def zentao_priority(value: str) -> int:
    text = str(value or "").strip().upper().removeprefix("P")
    try:
        priority = int(text)
    except ValueError:
        return 3
    return priority if 1 <= priority <= 4 else 3


def item_value(item: Any, key: str, *, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
