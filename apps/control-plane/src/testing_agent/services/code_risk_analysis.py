"""代码风险分析任务快照、GitLab 凭据下发与报告读取(工单 06/07,RC-4/RC-5)。

任务快照(创建 run 时一次性组装并固化)含:
- 需求文档(名称、类型、正文);
- 绑定清单:需求级仓库绑定 + RC-3 基线解析结果 + 创建时解析快照的
  connection_id(ADR-0007:快照记录实际执行人的个人连接引用，下发前重新校验);
- 现有测试内容:该需求下功能/API/UI 用例的名称/步骤/断言与最近执行结果
  (功能用例暂无执行记录、留空标注;API/UI 取最近一次 run 的 status 与
  完成时间,不带日志);
- GitLab 凭据获取指引(内部端点 URL)。

报告读取:worker 完成回调把风险报告 YAML 存入通用 run 表 `result_yaml`;
run 详情接口把 YAML 解析为 `report` 结构(四区块 + 各仓库
baselineCommit/headCommit + analyzedAt)供前端渲染。

凭据安全边界:解密后的 access_token 只存在于请求进程内存(任务创建时
用于远端分支校验、内部端点响应),不写入任务快照、不落盘、不入日志。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import (
    ErrIntegrationConnectionAuthFailed,
    ErrIntegrationConnectionNotFound,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.schemas.requirement import normalize_document_type
from testing_agent.services.ai_generate_task import (
    dump_run,
    requirement_source_content,
    worker_requirement_document_download_url,
)
from testing_agent.services.baseline_resolution import (
    BaselineResolutionService,
    RepoBaselineResolution,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.repo_gitlab_access import (
    RepoGitlabAccess,
    resolve_repo_gitlab_access,
)

FUNCTION_CASE_NO_RUN_NOTE = "功能用例暂无执行记录"
CONNECTION_UNRESOLVED_NOTE = "未解析到该仓库的 GitLab 凭据连接(群组绑定缺失或连接不可用)"


def dump_last_run(run: Any | None) -> dict[str, Any] | None:
    """用例最近一次 run:仅 status 与完成时间,不带日志(工单 06 口径)。"""
    if run is None:
        return None
    return {"status": run.status, "finishedAt": run.finished_at}


RISK_REPORT_SECTION_KEYS = {
    "changeOverview": ("changeOverview", "change_overview"),
    "risks": ("risks", "risk_list"),
    "affectedCases": ("affectedCases", "affected_cases"),
    "coverageGaps": ("coverageGaps", "coverage_gaps"),
    "repositories": ("repositories",),
    "analyzedAt": ("analyzedAt", "analyzed_at"),
}

RISK_REPORT_REPOSITORY_KEYS = {
    "repositoryId": ("repositoryId", "repository_id"),
    "branch": ("branch",),
    "baselineCommit": ("baselineCommit", "baseline_commit"),
    "headCommit": ("headCommit", "head_commit"),
}


def _risk_report_section(data: dict[str, Any], section: str) -> Any:
    for alias in RISK_REPORT_SECTION_KEYS[section]:
        if alias in data:
            return data[alias]
    return None


def _normalize_risk_report_repository(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    for canonical, aliases in RISK_REPORT_REPOSITORY_KEYS.items():
        value = None
        for alias in aliases:
            if alias in normalized:
                value = normalized[alias]
                break
        if value is None:
            continue
        normalized[canonical] = value
        for alias in aliases:
            if alias != canonical:
                normalized.pop(alias, None)
    return normalized


def parse_risk_report(result_yaml: str | None) -> dict[str, Any] | None:
    """把 worker 回传的风险报告 YAML 解析为前端渲染结构(工单 07,RC-5)。

    worker 契约:completed 回调的 `resultYaml` 携带报告 YAML,顶层含
    - `analyzedAt`:分析时间(字符串,原样透传);
    - `repositories`:每仓库 `repositoryId`/`branch`/`baselineCommit`/`headCommit`;
    - `changeOverview`(对象)/ `risks`、`affectedCases`、`coverageGaps`(列表)四区块。
    顶层键与仓库条目键均接受 camelCase/snake_case 拼写。
    为空、无法解析、不含任何报告区块、或已出现区块形态不符契约时返回
    None(任务详情仍可通过 `resultYaml` 原文读到回调内容)。
    """
    raw = str(result_yaml or "").strip()
    if not raw:
        return None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    sections = {key: _risk_report_section(data, key) for key in RISK_REPORT_SECTION_KEYS}
    if all(sections[key] is None for key in RISK_REPORT_SECTION_KEYS):
        return None
    # 已出现的区块形态必须符合契约,否则整体视为无法解析,不返回残缺结构。
    if sections["analyzedAt"] is not None and not isinstance(sections["analyzedAt"], str):
        return None
    if sections["changeOverview"] is not None and not isinstance(sections["changeOverview"], dict):
        return None
    for section in ("risks", "affectedCases", "coverageGaps", "repositories"):
        if sections[section] is not None and not isinstance(sections[section], list):
            return None
    repositories = sections["repositories"]
    if repositories is not None and any(not isinstance(item, dict) for item in repositories):
        return None
    return {
        "analyzedAt": sections["analyzedAt"],
        "repositories": [_normalize_risk_report_repository(item) for item in (repositories or [])],
        "changeOverview": sections["changeOverview"],
        "risks": sections["risks"],
        "affectedCases": sections["affectedCases"],
        "coverageGaps": sections["coverageGaps"],
    }


def dump_code_risk_analysis_run(run: Any) -> dict[str, Any]:
    """run 详情负载(任务详情接口口径):通用字段 + 解析后的 `report` 结构。"""
    payload = dump_run(run)
    payload["report"] = parse_risk_report(str(getattr(run, "result_yaml", "") or ""))
    return payload


class CodeRiskAnalysisService:
    def __init__(
        self,
        task_repository: AiGenerateTaskRepository,
        binding_repository: ResourceBindingRepository,
        baseline_resolution_service: BaselineResolutionService,
        integration_connection_service: IntegrationConnectionService,
        credential_cipher: IntegrationCredentialCipher,
    ):
        self.task_repository = task_repository
        self.binding_repository = binding_repository
        self.baseline_resolution_service = baseline_resolution_service
        self.integration_connection_service = integration_connection_service
        self.credential_cipher = credential_cipher

    async def build_snapshot(
        self,
        task: AiGenerateTask,
        run_id: str,
        worker_task_id: str,
        instruction: str | None = None,
        *,
        user_id: str,
        connection_ids: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """组装 code_risk_analysis 任务的 run 快照(创建时固化)。"""
        requirement = await self.task_repository.get_requirement(task.requirement_id)
        if requirement is None:
            raise ErrNotFound

        bindings = list(
            await self.binding_repository.list_active_repo_bindings_for_requirement(
                task.requirement_id
            )
        )
        repo_access = await self._resolve_repo_access(
            task.project_id, bindings, user_id, connection_ids or {}
        )
        resolutions = await self.baseline_resolution_service.resolve_requirement_bindings(
            task.requirement_id
        )
        by_binding = {row.binding.binding_id: row.resolution for row in resolutions}
        for binding in bindings:
            resolution = by_binding[binding.binding_id]
            if resolution.baseline_ref:
                access = repo_access[binding.binding_id]
                client = self.integration_connection_service.gitlab_resource_client
                result = await client.list_repository_branches(
                    access.base_url,
                    access.access_token,
                    binding.remote_resource_id,
                    search=resolution.baseline_ref,
                    page=1,
                    page_size=100,
                )
                if not any(
                    str(item.get("name") or "") == resolution.baseline_ref
                    for item in result.get("items", [])
                ):
                    from dataclasses import replace

                    by_binding[binding.binding_id] = replace(
                        resolution, error="基线分支不可访问，请管理员检查绑定"
                    )

        document_type = normalize_document_type(str(requirement.document_type or "text"))
        document_content = requirement_source_content(requirement)
        if not document_content and document_type == "docx":
            # 文档正文为空时按内部端点下发下载地址(worker token 鉴权,与
            # build_generate_run_snapshot 同口径),而不是用户态 /v1 下载地址。
            document_content = worker_requirement_document_download_url(worker_task_id)
        return {
            "taskId": task.task_id,
            "runId": run_id,
            "taskType": task.task_type,
            "name": task.name,
            "projectId": task.project_id,
            "sprintId": task.sprint_id,
            "requirementId": task.requirement_id,
            "sourceType": task.source_type,
            "instruction": task.instruction if instruction is None else instruction,
            "requirement": {
                "requirementId": requirement.requirement_id,
                "name": requirement.name,
                "documentType": document_type,
                "documentContent": document_content,
            },
            "bindings": [
                self._binding_entry(binding, by_binding.get(binding.binding_id), repo_access)
                for binding in bindings
            ],
            "existingTests": {
                "functionCases": await self._function_cases(task.requirement_id),
                "apiCases": await self._api_cases(task.requirement_id),
                "uiCases": await self._ui_cases(task.requirement_id),
            },
            "gitlabCredentialsUrl": (
                f"/internal/ai-worker/tasks/{worker_task_id}/gitlab-credentials"
            ),
        }

    async def _resolve_repo_access(
        self,
        project_id: str,
        bindings: Sequence[ResourceBinding],
        user_id: str,
        connection_ids: dict[str, str],
    ) -> dict[str, RepoGitlabAccess]:
        """按 ADR-0007 解析每个仓库的凭据(共用口径见 repo_gitlab_access)。"""
        access: dict[str, RepoGitlabAccess] = {}
        for binding in bindings:
            resolved = await resolve_repo_gitlab_access(
                self.binding_repository,
                self.integration_connection_service,
                self.credential_cipher,
                project_id,
                binding,
                user_id=user_id,
                connection_id=connection_ids.get(binding.instance_url, ""),
            )
            if resolved is not None:
                access[binding.binding_id] = resolved
        return access

    @staticmethod
    def _binding_entry(
        binding: ResourceBinding,
        resolution: RepoBaselineResolution | None,
        repo_access: dict[str, RepoGitlabAccess],
    ) -> dict[str, Any]:
        extra = binding.extra_json or {}
        access = repo_access.get(binding.binding_id)
        notes = [note for note in [resolution.note if resolution is not None else ""] if note]
        if access is None:
            notes.append(CONNECTION_UNRESOLVED_NOTE)
        return {
            "bindingId": binding.binding_id,
            "instanceUrl": binding.instance_url,
            "repositoryId": binding.remote_resource_id,
            "groupId": binding.remote_parent_id or "",
            "branch": str(extra.get("branch") or "").strip(),
            "baselineBranch": str(
                extra.get("baseline_branch") or extra.get("baselineBranch") or ""
            ).strip(),
            "baselineRef": resolution.baseline_ref if resolution is not None else None,
            "note": "；".join(notes),
            "error": resolution.error if resolution is not None else "",
            "connectionId": access.connection_id if access is not None else "",
        }

    async def _function_cases(self, requirement_id: str) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for suite in await self.task_repository.list_function_suites_by_requirement(requirement_id):
            for case in await self.task_repository.list_function_cases(suite.suite_id):
                cases.append(
                    {
                        "suiteId": suite.suite_id,
                        "suiteName": suite.name,
                        "caseId": case.case_id,
                        "title": case.title,
                        "module": case.module,
                        "preconditions": case.preconditions,
                        "steps": case.steps,
                        "expectedResults": case.expected_results,
                        "priority": case.priority,
                        "caseType": case.case_type,
                        "lastRun": None,
                        "runNote": FUNCTION_CASE_NO_RUN_NOTE,
                    }
                )
        return cases

    async def _api_cases(self, requirement_id: str) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for collection in await self.task_repository.list_api_collections_by_requirement(
            requirement_id
        ):
            for case in await self.task_repository.list_api_cases(collection.collection_id):
                rules = await self.task_repository.list_api_assert_rules(case.case_id)
                latest = await self.task_repository.get_latest_api_case_run(case.case_id)
                cases.append(
                    {
                        "collectionId": collection.collection_id,
                        "collectionName": collection.name,
                        "caseId": case.case_id,
                        "name": case.name,
                        "description": case.description,
                        "method": case.method,
                        "urlTemplate": case.url_template,
                        "assertRules": [
                            {
                                "name": rule.name,
                                "assertSource": rule.assert_source,
                                "targetExpr": rule.target_expr,
                                "comparator": rule.comparator,
                                "expectedValue": rule.expected_value,
                            }
                            for rule in rules
                        ],
                        "lastRun": dump_last_run(latest),
                    }
                )
        return cases

    async def _ui_cases(self, requirement_id: str) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for suite in await self.task_repository.list_ui_suites_by_requirement(requirement_id):
            for case in await self.task_repository.list_ui_cases(suite.suite_id):
                latest = await self.task_repository.get_latest_ui_case_run(case.case_id)
                cases.append(
                    {
                        "suiteId": suite.suite_id,
                        "suiteName": suite.name,
                        "caseId": case.case_id,
                        "name": case.name,
                        "stepsJson": case.steps_json,
                        "lastRun": dump_last_run(latest),
                    }
                )
        return cases


async def gitlab_credentials_payload(
    session: AsyncSession,
    task_id: str,
    project_id: str,
    bindings: list[Any],
    cipher: IntegrationCredentialCipher | None,
    *,
    user_id: str,
) -> dict[str, Any]:
    """按任务快照下发的绑定清单组装凭据负载:同一 connection 聚合一个条目。

    access_token 为响应时解密,仅驻内存;connection 缺失/解密失败返回
    3401 系列结构化错误。
    """
    grouped: dict[str, dict[str, Any]] = {}
    for binding in bindings or []:
        if not isinstance(binding, dict):
            continue
        connection_id = str(binding.get("connectionId") or "")
        repository_id = str(binding.get("repositoryId") or "")
        if not connection_id or not repository_id:
            continue
        if connection_id not in grouped:
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.connection_id == connection_id,
                    IntegrationConnection.provider == "gitlab",
                    IntegrationConnection.project_id.in_(("", project_id)),
                    IntegrationConnection.user_id == user_id,
                    IntegrationConnection.status == "active",
                )
            )
            if connection is None:
                raise ErrIntegrationConnectionNotFound
            if cipher is None:
                raise dynamic_error(ErrIntegrationConnectionAuthFailed, "GitLab 凭据解密密钥未配置")
            try:
                access_token = cipher.decrypt(connection.access_token)
            except ValueError as exc:
                raise dynamic_error(
                    ErrIntegrationConnectionAuthFailed,
                    "GitLab 凭据解密失败,请重新保存该连接",
                ) from exc
            grouped[connection_id] = {
                "connectionId": connection_id,
                "baseUrl": connection.base_url,
                "accessToken": access_token,
                "repositoryIds": [],
            }
        grouped[connection_id]["repositoryIds"].append(repository_id)
    return {
        "taskId": task_id,
        "bindings": list(bindings or []),
        "credentials": list(grouped.values()),
    }
