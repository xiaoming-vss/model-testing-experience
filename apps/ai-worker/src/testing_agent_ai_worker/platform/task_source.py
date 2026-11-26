"""Platform task source and protocol adaptation.

调用链路：
- `TaskPoller.poll -> TaskService.poll_one -> HttpClaimTaskSource.poll_task`
- `poll_task -> claim -> snapshot -> llm-credentials`
- `poll_task -> _to_domain_task`

这里的职责是把平台协议对象收敛成 worker 内部 `Task`，不承担实际执行逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from testing_agent_ai_worker.core.errors import (
    safe_credential_error,
    safe_validation_error,
)
from testing_agent_ai_worker.models.task import (
    ExistingTestCases,
    GitlabCredentials,
    LlmCredentials,
    RepositoryBinding,
    RequirementInput,
    Task,
    TaskPayload,
)
from testing_agent_ai_worker.platform.errors import TaskSourceError
from testing_agent_ai_worker.platform.http_client import PlatformHttpClient
from testing_agent_ai_worker.platform.schemas import (
    PlatformClaimTask,
    PlatformGitlabCredentialsResponse,
    PlatformLlmCredentials,
    PlatformSnapshotResponse,
)


def parse_gitlab_credentials(payload: dict[str, Any] | None) -> list[GitlabCredentials]:
    """解析 gitlab-credentials 端点响应。

    同一 connectionId 出现多次时聚合 repositoryIds(控制面按 connectionId 聚合,这里再做
    一次防御性合并,保证内部模型每个连接只有一个条目)。
    """

    if not payload:
        return []
    response = PlatformGitlabCredentialsResponse.model_validate(
        {**payload, "credentials": payload.get("credentials") or []}
    )
    merged: dict[str, GitlabCredentials] = {}
    for item in response.credentials:
        # 仅在 connectionId 非空时聚合;缺 connectionId 的条目不参与合并,各自独立,
        # 避免把不同连接因 base_url 相同而误并为一条。
        if not item.connection_id:
            merged[f"standalone-{len(merged)}"] = GitlabCredentials(
                connection_id="",
                base_url=item.base_url,
                access_token=item.access_token,
                repository_ids=list(item.repository_ids),
            )
            continue
        existing = merged.get(item.connection_id)
        if existing is None:
            merged[item.connection_id] = GitlabCredentials(
                connection_id=item.connection_id,
                base_url=item.base_url,
                access_token=item.access_token,
                repository_ids=list(item.repository_ids),
            )
            continue
        for repository_id in item.repository_ids:
            if repository_id not in existing.repository_ids:
                existing.repository_ids.append(repository_id)
    return list(merged.values())


class TaskSource(Protocol):
    def poll_task(self) -> Task | None: ...


@dataclass(slots=True)
class HttpClaimTaskSource:
    client: PlatformHttpClient
    claim_path: str
    snapshot_path_template: str
    llm_credentials_path_template: str
    worker_id: str

    def poll_task(self) -> Task | None:
        """执行一次完整的平台任务获取流程。"""

        try:
            claim_payload = self.client.post(
                self.claim_path,
                json_body={"workerId": self.worker_id},
            )
            if not claim_payload:
                return None

            try:
                claimed_task = PlatformClaimTask.model_validate(claim_payload)
            except ValidationError as exc:
                raise TaskSourceError(
                    safe_validation_error(exc, subject="任务领取响应校验失败")
                ) from None
            if not claimed_task.attempt_id.strip():
                raise TaskSourceError(
                    f"任务身份缺失(attemptId): task_id={claimed_task.task_id}; "
                    "请确认控制面与 AI Worker 同为最新版本"
                )
            snapshot_payload = self.client.get(
                self.snapshot_path_template.format(task_id=claimed_task.task_id)
            )
            if not snapshot_payload:
                raise TaskSourceError(f"任务快照为空: task_id={claimed_task.task_id}")

            try:
                snapshot_response = PlatformSnapshotResponse.model_validate(snapshot_payload)
            except ValidationError as exc:
                raise TaskSourceError(
                    safe_validation_error(exc, subject="任务快照校验失败")
                ) from None
            task = self._to_domain_task(
                claimed_task,
                snapshot_response,
                raw_snapshot=snapshot_payload,
            )

            if claimed_task.llm_connection_id and self.llm_credentials_path_template:
                try:
                    credentials = self._fetch_llm_credentials(task.task_id)
                    task.payload.llm_credentials = credentials
                except Exception as exc:
                    task.credential_error = (
                        str(exc) if isinstance(exc, TaskSourceError) else safe_credential_error(exc)
                    )

            return task
        except httpx.TimeoutException as exc:  # pragma: no cover
            raise TaskSourceError(
                f"领取任务超时: path={self.claim_path} timeout={self.client.timeout_seconds}s"
            ) from exc
        except Exception as exc:
            if isinstance(exc, TaskSourceError):
                raise
            raise TaskSourceError(f"领取任务失败: {type(exc).__name__}") from exc

    def _fetch_llm_credentials(self, task_id: str) -> LlmCredentials:
        """补拉模型凭证。

        这里和 claim/snapshot 分开调用，是为了继续兼容现有平台的三段式协议。
        """

        path = self.llm_credentials_path_template.format(task_id=task_id)
        payload = self.client.get_with_retry(path)
        if not payload:
            raise TaskSourceError(f"LLM 凭证响应为空: task_id={task_id}")
        try:
            credentials = PlatformLlmCredentials.model_validate(payload)
        except ValidationError as exc:
            raise TaskSourceError(
                safe_validation_error(exc, subject="LLM 凭证响应校验失败")
            ) from None
        return LlmCredentials(
            model=credentials.model_id,
            api_key=credentials.api_key,
            base_url=credentials.base_url,
        )

    def _to_domain_task(
        self,
        claimed_task: PlatformClaimTask,
        snapshot_response: PlatformSnapshotResponse,
        *,
        raw_snapshot: dict[str, object],
    ) -> Task:
        """把平台 claim/snapshot 响应映射成内部任务模型。

        字段优先级需要兼容平台响应位置漂移，因此会做多层回退合并。
        """

        snapshot_task = snapshot_response.run

        checkpoint_enabled = (
            snapshot_response.checkpoint_enabled
            if snapshot_response.checkpoint_enabled is not None
            else bool(claimed_task.checkpoint_enabled)
        )
        current_stage = snapshot_response.current_stage or claimed_task.current_stage
        config_json = snapshot_response.config_json or claimed_task.config_json
        task_type = snapshot_response.task_type
        if task_type.strip().lower() == "functional_case_generate":
            # 功能用例消费的是需求理解 JSON，不是原始需求文档；documentType 不参与格式判断。
            document_type = ""
            source_format, source_format_version = self._resolve_functional_source_format(
                snapshot_task
            )
        else:
            document_type = self._resolve_document_type(snapshot_task)
            source_format, source_format_version = "", ""
        source_type = self._resolve_source_type(task_type, snapshot_task, document_type)

        return Task(
            task_id=claimed_task.task_id,
            attempt_id=claimed_task.attempt_id or snapshot_task.attempt_id,
            generate_task_id=claimed_task.generate_task_id or snapshot_task.generate_task_id,
            task_type=task_type,
            name=snapshot_task.name,
            project_id=claimed_task.project_id or snapshot_task.project_id,
            sprint_id=claimed_task.sprint_id or snapshot_task.sprint_id,
            requirement_id=claimed_task.requirement_id or snapshot_task.requirement_id,
            lease_seconds=claimed_task.lease_seconds,
            checkpoint_enabled=checkpoint_enabled,
            current_stage=current_stage,
            config_json=config_json,
            candidate_input=(
                snapshot_response.candidate_input.model_dump(mode="json", by_alias=True)
                if snapshot_response.candidate_input is not None
                else None
            ),
            requirement_input=(
                RequirementInput.model_validate(snapshot_task.requirement)
                if snapshot_task.requirement
                else None
            ),
            bindings=[RepositoryBinding.model_validate(item) for item in snapshot_task.bindings],
            existing_tests=(
                ExistingTestCases.model_validate(snapshot_task.existing_tests)
                if snapshot_task.existing_tests
                else ExistingTestCases()
            ),
            gitlab_credentials_url=snapshot_task.gitlab_credentials_url,
            payload=TaskPayload(
                openapi_content=snapshot_task.source_content,
                source_content=snapshot_task.source_content,
                interfaces=snapshot_task.interfaces,
                software_repositories=snapshot_task.software_repositories,
                document_download_url=snapshot_task.document_download_url,
                document_type=document_type,
                source_type=source_type,
                source_format=source_format,
                source_format_version=source_format_version,
                target_scope=snapshot_task.target_scope,
                extra_instruction=snapshot_task.instruction,
                daily_metrics=snapshot_task.daily_metrics,
                metadata={
                    "workflowVersion": snapshot_task.workflow_version,
                    "uiWorkflowVersion": (raw_snapshot.get("run") or {}).get("uiWorkflowVersion"),
                    "apiWorkflowVersion": (raw_snapshot.get("run") or {}).get("apiWorkflowVersion"),
                    "functionalCases": (raw_snapshot.get("run") or {}).get("functionalCases", []),
                    "documentFilename": (raw_snapshot.get("run") or {}).get("documentFilename", ""),
                    "documentFileId": (raw_snapshot.get("run") or {}).get("documentFileId", ""),
                    "sourceRepository": snapshot_task.source_repository or {},
                    "sourceCommit": snapshot_task.source_commit,
                },
            ),
        )

    @staticmethod
    def _resolve_functional_source_format(snapshot_task: object) -> tuple[str, str]:
        source_format = getattr(snapshot_task, "source_format", "").strip().lower()
        source_format_version = str(
            getattr(snapshot_task, "source_format_version", "") or ""
        ).strip()
        return source_format, source_format_version

    @staticmethod
    def _resolve_document_type(snapshot_task: object) -> str:
        document_type = getattr(snapshot_task, "document_type", "").strip().lower()
        if document_type:
            return HttpClaimTaskSource._normalize_document_type(document_type)

        source_type = getattr(snapshot_task, "source_type", "").strip().lower()
        return HttpClaimTaskSource._normalize_document_type(source_type)

    @staticmethod
    def _resolve_source_type(task_type: str, snapshot_task: object, document_type: str) -> str:
        normalized_task_type = task_type.strip().lower()
        source_type = getattr(snapshot_task, "source_type", "").strip().lower()
        if normalized_task_type == "api_case_generate":
            return source_type or "openapi"
        if normalized_task_type == "functional_case_generate":
            # 功能链路的 sourceType 是任务来源标记，不是正文格式。
            return source_type or "requirement"
        if normalized_task_type == "requirement_analysis":
            return document_type
        return source_type

    @staticmethod
    def _normalize_document_type(source_type: str) -> str:
        if source_type in {"word", "docx"}:
            return "word"
        if source_type in {"text", "txt"}:
            return "text"
        return source_type
