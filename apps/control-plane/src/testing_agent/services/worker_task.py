from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.worker_context import AiWorkerContext, ApiWorkerContext
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.ai_execution.writer import ExecutionWriter, SqlExecutionWriter
from testing_agent.services.code_risk_analysis import gitlab_credentials_payload
from testing_agent.services.execution_secrets import private_payload, redact
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.worker import (
    LEASE_SECONDS,
    apply_event_to_task,
    build_snapshot,
    complete_domain_run,
    find_task,
    llm_credentials_payload,
    parse_event_time,
    project_skill_worker_payload,
    task_payload,
    update_task_claimed,
)
from testing_agent.services.worker_authorization import authorize_execution
from testing_agent.services.worker_domains import ai as ai_domain
from testing_agent.services.worker_domains import api as api_domain
from testing_agent.services.worker_domains import ui as ui_domain
from testing_agent.services.worker_domains.events import ensure_final_status

AI_LEASE_SECONDS = 30


def ensure_worker_match(task, worker_id: str | None) -> None:
    if not worker_id or not worker_id.strip():
        raise ErrBadRequest()
    if not task.worker_id or task.worker_id != worker_id:
        raise ErrForbidden()
    if task.status not in {"claimed", "running"}:
        raise ErrBadRequest()
    lease = getattr(task, "lease_expires_at", None)
    if lease is not None:
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=UTC)
        if lease <= datetime.now(UTC):
            raise ErrBadRequest()


def ensure_task_id(task, body: WorkerTaskEventRequest) -> None:
    if body.task_id and body.task_id != task.task_id:
        raise ErrBadRequest()


class WorkerTaskService:
    def __init__(
        self,
        repository: WorkerTaskRepository,
        credential_cipher: IntegrationCredentialCipher | None = None,
        execution_writer: ExecutionWriter | None = None,
    ):
        self.repository = repository
        self.execution = execution_writer or SqlExecutionWriter()
        self.credential_cipher = credential_cipher

    async def validate_ui_artifacts(self, task_id, body):
        import re

        from testing_agent.models.stored_file import StoredFile

        paths = [body.trace_path] if body.trace_path else []
        for step in body.step_results or []:
            if isinstance(step, dict) and step.get("screenshotPath"):
                paths.append(step["screenshotPath"])
        for path in paths:
            match = re.fullmatch(r"/v1/files/([a-zA-Z0-9-]+)/download", path)
            if not match:
                raise ErrBadRequest()
            row = await self.repository.session.scalar(
                select(StoredFile).where(
                    StoredFile.file_id == match[1],
                    StoredFile.status == "attached",
                    StoredFile.resource_type == "ui_worker_task",
                    StoredFile.resource_id == task_id,
                )
            )
            if row is None:
                raise ErrForbidden()

    async def _guard_ai_event(self, task, run):
        from testing_agent.models.ai_generate_task import AiGenerateTaskRun
        from testing_agent.services.ai_execution import require_current_worker

        if isinstance(run, AiGenerateTaskRun):
            await self.repository.session.run_sync(
                lambda session: require_current_worker(session, run, task)
            )

    async def expire_leases(self, domain: str):
        for task in await self.repository.expired_tasks(domain):
            if domain == "ai":
                run = await self.repository.get_ai_run(task.run_id)
                if run is not None:
                    # An obsolete queue entry must never fail a newer attempt.
                    try:
                        await self._guard_ai_event(task, run)
                    except type(ErrBadRequest):
                        task.status = "failed"
                        task.error_message = "Worker 租约过期"
                        task.finished_at = datetime.now(UTC)
                        continue
            body = WorkerTaskEventRequest(
                worker_id=task.worker_id,
                status="failed",
                error_message="Worker 心跳超时，执行已终止，请重试",
            )
            await apply_event_to_task(task, body, "failed")
            await complete_domain_run(self.repository.session, domain, task, body)
            if domain == "ai" and run is not None:
                await self.execution.save(
                    self.repository.session,
                    run,
                    intent=ExecutionIntent(worker_event_id=task.task_id),
                    worker=task,
                )
        await self.repository.commit()

    async def claim(self, domain: str, body: WorkerClaimRequest) -> dict | None:
        if not body.worker_id or not body.worker_id.strip():
            raise ErrBadRequest()
        if isinstance(self.repository, WorkerTaskRepository):
            await self.expire_leases(domain)
        task = await self.repository.claim_pending(domain)
        if task is None:
            return None
        try:
            await authorize_execution(self.repository.session, task, pending=True)
        except type(ErrForbidden):
            return None
        context = await self.repository.execution_context(task)
        await update_task_claimed(task, body)
        if domain == "api":
            if not isinstance(context, ApiWorkerContext):
                raise ErrBadRequest()
            await api_domain.mark_claimed(self.repository, task, context)
        if domain == "ai":
            if not isinstance(context, AiWorkerContext):
                raise ErrBadRequest()
            task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=AI_LEASE_SECONDS)
            ai_run = await ai_domain.mark_claimed(self.repository, task)
            await self.execution.save(self.repository.session, ai_run, worker=task)
            await self.repository.commit()
            await self.repository.refresh(task)
            return ai_domain.claim_payload(task, ai_run, context, lease_seconds=AI_LEASE_SECONDS)
        await self.repository.commit()
        await self.repository.refresh(task)
        payload = task_payload(task, context)
        payload["leaseSeconds"] = LEASE_SECONDS
        return payload

    async def snapshot(self, domain: str, task_id: str) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        await authorize_execution(self.repository.session, task)
        payload = await build_snapshot(self.repository.session, domain, task)
        await self.repository.commit()
        return payload

    async def started(self, domain: str, task_id: str, body: WorkerTaskEventRequest) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        started_at = parse_event_time(body.started_at)
        if body.started_at and started_at is None:
            raise ErrBadRequest()
        if domain == "ai":
            guarded_run = await self.repository.get_ai_run(task.run_id)
            if guarded_run is None:
                raise ErrNotFound()
            await self._guard_ai_event(task, guarded_run)
        await apply_event_to_task(task, body, "running")
        if started_at is not None:
            task.started_at = started_at
            task.heartbeat_at = started_at
            task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        if domain == "api":
            await api_domain.mark_started(self.repository, task, started_at)
        if domain == "ai":
            ai_run = await ai_domain.mark_started(self.repository, task, started_at)
        if domain == "ui":
            await ui_domain.mark_started(self.repository.session, task, started_at)
        if domain == "ai":
            assert ai_run is not None
            await self.execution.save(
                self.repository.session,
                ai_run,
                intent=ExecutionIntent(worker_event_id=task.task_id),
                worker=task,
            )
        await self.repository.commit()
        return {"taskId": task_id, "workerId": body.worker_id}

    async def heartbeat(self, domain: str, task_id: str, body: WorkerTaskEventRequest) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if domain == "ai":
            ai_run = await self.repository.get_ai_run(task.run_id)
            if ai_run is None:
                raise ErrNotFound()
            await self._guard_ai_event(task, ai_run)
        heartbeat_at = parse_event_time(body.heartbeat_at)
        if body.heartbeat_at and heartbeat_at is None:
            raise ErrBadRequest()
        await apply_event_to_task(task, body, task.status)
        if heartbeat_at is not None:
            task.heartbeat_at = datetime.now(UTC)
            task.lease_expires_at = task.heartbeat_at + timedelta(seconds=LEASE_SECONDS)
        await self.repository.commit()
        return {"taskId": task_id, "workerId": body.worker_id}

    async def complete(self, domain: str, task_id: str, body: WorkerTaskEventRequest) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        authority = await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if domain == "ui":
            await self.validate_ui_artifacts(task_id, body)
        status = ensure_final_status(body.status, {"success", "failed", "error", "canceled"})
        if domain == "ai":
            guarded_run = await self.repository.get_ai_run(task.run_id)
            if guarded_run is None:
                raise ErrNotFound()
            await self._guard_ai_event(task, guarded_run)
            if task.task_type == "requirement_analysis" and status == "success":
                from testing_agent.services.requirement_analysis_contracts import (
                    validate_run_output,
                )

                if guarded_run.current_stage != "feature_understanding":
                    raise ErrBadRequest()
                validate_run_output(
                    guarded_run, config=body.config_json, result=body.result_yaml, final=True
                )
        await apply_event_to_task(task, body, status)
        await complete_domain_run(self.repository.session, domain, task, body)
        if domain == "api":
            task.error_message = redact(
                task.error_message, private_payload(authority.run).get("secrets", [])
            )
        if domain == "ai":
            assert guarded_run is not None
            await self.execution.save(
                self.repository.session,
                guarded_run,
                intent=ExecutionIntent(worker_event_id=task.task_id),
                worker=task,
            )
        await self.repository.commit()
        return {"taskId": task_id, "workerId": body.worker_id, "status": status}

    async def start_api_collection_item(
        self, task_id: str, item_id: str, body: WorkerTaskEventRequest
    ) -> dict:
        task = await find_task(self.repository.session, "api", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        await api_domain.start_item(self.repository, task, item_id, body)
        await self.repository.commit()
        return {"taskId": task_id, "itemId": item_id, "workerId": body.worker_id}

    async def complete_api_collection_item(
        self, task_id: str, item_id: str, body: WorkerTaskEventRequest
    ) -> dict:
        task = await find_task(self.repository.session, "api", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        status = await api_domain.complete_item(
            self.repository, task, item_id, body, id_factory=new_id
        )
        await self.repository.commit()
        return {"taskId": task_id, "itemId": item_id, "status": status}

    async def start_ui_suite_item(
        self, task_id: str, item_id: str, body: WorkerTaskEventRequest
    ) -> dict:
        task = await find_task(self.repository.session, "ui", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        await ui_domain.start_item(self.repository, task, item_id, body)
        await self.repository.commit()
        return {"taskId": task_id, "itemId": item_id, "workerId": body.worker_id}

    async def complete_ui_suite_item(
        self, task_id: str, item_id: str, body: WorkerTaskEventRequest
    ) -> dict:
        task = await find_task(self.repository.session, "ui", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        await self.validate_ui_artifacts(task_id, body)
        ensure_task_id(task, body)
        status = await ui_domain.complete_item(self.repository, task, item_id, body)
        await self.repository.commit()
        return {"taskId": task_id, "itemId": item_id, "status": status}

    async def list_project_skills(self, project_id: str) -> dict:
        rows = await self.repository.list_project_skills(project_id)
        return {
            "projectId": project_id,
            "skills": [project_skill_worker_payload(row) for row in rows],
        }

    async def _ai_worker_task(self, task_id: str):
        if hasattr(self.repository, "get_worker_task"):
            task = await self.repository.get_worker_task("ai", task_id)
            if task is None:
                raise ErrNotFound()
            await authorize_execution(self.repository.session, task)
            return task
        return await find_task(self.repository.session, "ai", task_id)

    async def llm_credentials(self, task_id: str) -> dict:
        task = await find_task(self.repository.session, "ai", task_id)
        authority = await authorize_execution(self.repository.session, task)
        context = await self.repository.execution_context(task)
        if not isinstance(context, AiWorkerContext):
            raise ErrNotFound()
        connection = await require_personal_connection(
            self.repository.session,
            authority.actor,
            "llm",
            str(context.llm_connection_id or ""),
            authority.project_id,
        )
        payload = llm_credentials_payload(task_id, connection, self.credential_cipher)
        if not str(payload.get("apiKey") or "").strip():
            from testing_agent.services.worker_authorization import fail_authorization

            await fail_authorization(self.repository.session, task, authority)
            await self.repository.commit()
            raise ErrForbidden()
        return payload

    async def gitlab_credentials(self, task_id: str) -> dict:
        """代码风险分析任务的 GitLab 凭据与绑定清单下发(凭据按快照复现)。

        绑定清单与 connection_id 取自任务创建时的 run 快照;access_token
        响应时解密,仅驻内存、不落盘、不入日志。
        """
        task = await find_task(self.repository.session, "ai", task_id)
        await authorize_execution(self.repository.session, task)
        if task.task_type != "code_risk_analysis":
            raise ErrNotFound()
        run = await self.repository.get_ai_run(task.run_id)
        if run is None:
            raise ErrNotFound()
        snapshot = run.snapshot_json or {}
        bindings = snapshot.get("bindings") or []
        return await gitlab_credentials_payload(
            self.repository.session,
            task.task_id,
            run.project_id,
            list(bindings),
            self.credential_cipher,
            user_id=(await authorize_execution(self.repository.session, task)).actor,
        )

    async def requirement_document(self, task_id: str):
        task = await self._ai_worker_task(task_id)
        if task.task_type not in {
            "requirement_analysis",
            "functional_case_generate",
            "ui_case_generate",
            "code_risk_analysis",
        }:
            raise ErrNotFound()
        run = await self.repository.get_ai_run(task.run_id)
        if run is None or not run.requirement_id:
            raise ErrNotFound()
        if task.task_type == "ui_case_generate":
            context = await self.repository.execution_context(task)
            if not isinstance(context, AiWorkerContext) or run.task_id != context.generate_task_id:
                raise ErrNotFound()
        requirement = await self.repository.get_requirement(run.requirement_id)
        if requirement is None:
            raise ErrNotFound()
        snapshot = getattr(run, "snapshot_json", None) or {}
        if task.task_type == "requirement_analysis" and snapshot.get("workflowVersion") == 2:
            original_file = snapshot.get("documentFileId")
            original_hash = snapshot.get("documentHash")
            if (original_file and original_file != requirement.document_file_id) or (
                original_hash and original_hash != requirement.document_hash
            ):
                from testing_agent.core.errors import AppError

                raise AppError(409, "原始需求文件已变更，请发起新运行；历史产物仍保留", 409)
        if not getattr(requirement, "document_file_id", ""):
            from testing_agent.core.errors import ErrRequirementFileMissing

            raise ErrRequirementFileMissing()
        return requirement

    async def source_archive(self, task_id: str):
        task = await self._ai_worker_task(task_id)
        if task.task_type != "ui_case_generate":
            raise ErrNotFound()
        run = await self.repository.get_ai_run(task.run_id)
        context = await self.repository.execution_context(task)
        if (
            run is None
            or not isinstance(context, AiWorkerContext)
            or run.task_id != context.generate_task_id
            or not run.task_id
        ):
            raise ErrNotFound()
        file_id = (run.snapshot_json or {}).get("sourceArchiveFileId")
        if not file_id:
            from testing_agent.core.errors import AppError

            raise AppError(409, "运行未关联 S3 源码包，请重新上传源码包并发起新运行", 409)
        return file_id

    async def progress(self, task_id: str, body: WorkerProgressRequest) -> dict:
        task = await find_task(self.repository.session, "ai", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        if body.task_id and body.task_id != task.task_id:
            raise ErrBadRequest()
        run = await self.repository.get_ai_run(task.run_id)
        if run:
            await self._guard_ai_event(task, run)
            ai_domain.apply_progress(run, task, body, lease_seconds=AI_LEASE_SECONDS)
        if run is not None:
            await self.execution.save(
                self.repository.session,
                run,
                intent=ExecutionIntent(worker_event_id=task.task_id),
                worker=task,
            )
        await self.repository.commit()
        return {"taskId": task_id}
