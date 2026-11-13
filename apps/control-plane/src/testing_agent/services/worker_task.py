from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from testing_agent.core.enums import RUN_CLOSED_STATUSES, RUN_TERMINAL_STATUSES, RunStatus
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrForbidden,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.worker_context import ApiWorkerContext
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.code_risk_analysis import gitlab_credentials_payload
from testing_agent.services.execution_secrets import private_payload, redact
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService
from testing_agent.services.standalone_worker_service import StandaloneWorkerService
from testing_agent.services.test_run_notifications import (
    notify_run_changed,
    notify_task_control,
    notify_ui_debug_execution_finished,
)
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
from testing_agent.services.worker_domains import api as api_domain
from testing_agent.services.worker_domains import ui as ui_domain
from testing_agent.services.worker_domains.events import ensure_final_status
from testing_agent.services.worker_domains.guard import ensure_task_id, ensure_worker_match

logger = logging.getLogger(__name__)


class WorkerTaskService:
    def __init__(
        self,
        repository: WorkerTaskRepository,
        credential_cipher: IntegrationCredentialCipher | None = None,
    ):
        self.repository = repository
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

    async def expire_leases(self, domain: str) -> int:
        tasks = await self.repository.expired_tasks(domain)
        processed = []
        for task in tasks:
            if domain == "ai":
                standalone = StandaloneWorkerService(self.repository.session)
                if await standalone.is_standalone(task):
                    await standalone.retire(task, "Worker 心跳超时，执行已终止，请重试")
                    processed.append(task)
                    continue
                direct = DirectStageWorkerService(self.repository.session)
                if await direct.is_direct(task):
                    await direct.expire(task)
                    processed.append(task)
                    continue
                logger.warning("AI 队列 %s 未关联有效的阶段尝试，租约未处理", task.task_id)
                continue
            final_status = "error" if domain in {"api", "ui"} else "failed"
            body = WorkerTaskEventRequest(
                worker_id=task.worker_id,
                status=final_status,
                error_message="Worker 心跳超时，执行已终止，请重试",
            )
            if domain in {"api", "ui"}:
                from testing_agent.services.test_run_stop import finish_stopped_items

                await finish_stopped_items(self.repository.session, task, interrupted=True)
            await apply_event_to_task(task, body, final_status)
            await complete_domain_run(self.repository.session, domain, task, body)
            processed.append(task)
        await self.repository.commit()
        for task in processed:
            await notify_run_changed(domain, task.run_id)
            if domain in {"api", "ui"}:
                await notify_task_control(task.task_id)
            if domain == "api" and task.task_type == "api_case_debug":
                api_run = await self.repository.get_api_run(task.run_id)
                if api_run is not None and api_run.trigger_type == "live_debug":
                    from testing_agent.services.live_debug_cleanup import finish_api_debug

                    await finish_api_debug(self.repository.session, task.task_id)
            elif domain == "ui" and task.task_type == "case_debug":
                ui_run = await self.repository.get_ui_case_run(task.run_id)
                if ui_run is not None and ui_run.trigger_type == "live_debug":
                    from testing_agent.services.live_debug_cleanup import finish_ui_debug

                    await finish_ui_debug(self.repository.session, task.task_id)
        return len(processed)

    async def claim(self, domain: str, body: WorkerClaimRequest) -> dict | None:
        if not body.worker_id or not body.worker_id.strip():
            raise ErrBadRequest()
        task = await self.repository.claim_pending(domain)
        return await self._claim_task(domain, task, body)

    async def claim_api_ui(self, body: WorkerClaimRequest) -> dict | None:
        """Claim the oldest API/UI task with the same lease and authorization checks."""
        if not body.worker_id or not body.worker_id.strip():
            raise ErrBadRequest()
        # Authorization may retire a queued task; keep looking so a rejected
        # task does not make this worker sleep while later work is available.
        for _ in range(100):
            task = await self.repository.claim_oldest_api_ui()
            if task is None:
                return None
            payload = await self._claim_task(task.domain, task, body)
            if payload is not None:
                return payload
        return None

    async def _claim_task(self, domain: str, task: WorkerTask | None, body: WorkerClaimRequest):
        if task is None:
            return None
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                try:
                    return await standalone.claim(task, body)
                except AppError as exc:
                    if exc.code == ErrForbidden.code:
                        return None
                    raise
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                try:
                    return await direct.claim(task, body)
                except AppError as exc:
                    if exc.code == ErrForbidden.code:
                        return None
                    raise
            raise dynamic_error(
                ErrBadRequest, "AI 队列未关联有效的阶段尝试，请停止 Worker 并完成切换"
            )
        try:
            authority = await authorize_execution(self.repository.session, task, pending=True)
        except type(ErrForbidden):
            return None
        run = authority.run
        direct_debug = (
            domain == "api"
            and task.task_type == "api_case_debug"
            and isinstance(run, ApiCaseRun)
            and run.trigger_type == "live_debug"
            and not run.collection_run_id
        )
        context = (
            ApiWorkerContext(run.case_id, run.collection_id, None)
            if direct_debug
            else await self.repository.execution_context(task)
        )
        await update_task_claimed(task, body)
        if domain == "api":
            if not isinstance(context, ApiWorkerContext):
                raise ErrBadRequest()
            if direct_debug:
                run.status = RunStatus.QUEUED.value
            else:
                await api_domain.mark_claimed(self.repository, task, context)
        await self.repository.commit()
        payload = task_payload(task, context)
        payload["leaseSeconds"] = LEASE_SECONDS
        await notify_run_changed(domain, task.run_id)
        return payload

    async def snapshot(self, domain: str, task_id: str) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                payload = await standalone.snapshot(task)
                await self.repository.commit()
                return payload
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                payload = await direct.snapshot(task)
                await self.repository.commit()
                return payload
            raise ErrNotFound()
        await authorize_execution(self.repository.session, task)
        payload = await build_snapshot(self.repository.session, domain, task)
        await self.repository.commit()
        return payload

    async def started(self, domain: str, task_id: str, body: WorkerTaskEventRequest) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                return await standalone.started(task, body)
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                return await direct.started(task, body)
            raise ErrNotFound()
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if task.status in RUN_TERMINAL_STATUSES:
            # A late start must not reopen a run that already finished.
            return {"taskId": task_id, "workerId": body.worker_id}
        if body.run_id and body.run_id != task.run_id:
            raise ErrBadRequest()
        if domain in {"api", "ui"} and task.status == "stopping":
            return {"taskId": task_id, "workerId": body.worker_id}
        started_at = parse_event_time(body.started_at)
        if body.started_at and started_at is None:
            raise ErrBadRequest()
        await apply_event_to_task(task, body, "running")
        if started_at is not None:
            task.started_at = started_at
            task.heartbeat_at = started_at
            task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        if domain == "api":
            await api_domain.mark_started(self.repository, task, started_at)
        if domain == "ui":
            await ui_domain.mark_started(self.repository.session, task, started_at)
        await self.repository.commit()
        await notify_run_changed(domain, task.run_id)
        return {"taskId": task_id, "workerId": body.worker_id}

    async def control_state(self, domain: str, task_id: str, worker_id: str) -> dict:
        """Read stop intent only for the current, authorized lease holder."""
        task = await find_task(self.repository.session, domain, task_id)
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                await standalone.authorize(task)
                ensure_worker_match(task, worker_id)
                return {"stopRequested": False}
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                await direct.authorize(task)
                ensure_worker_match(task, worker_id)
                return {"stopRequested": False}
            raise ErrNotFound()
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, worker_id)
        return {"stopRequested": task.status == "stopping"}

    async def heartbeat(self, domain: str, task_id: str, body: WorkerTaskEventRequest) -> dict:
        task = await find_task(self.repository.session, domain, task_id)
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                return await standalone.heartbeat(task, body)
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                return await direct.heartbeat(task, body)
            raise ErrNotFound()
        if task.status in RUN_TERMINAL_STATUSES:
            # A late heartbeat must not rewrite finished_at or extend the lease.
            return {"taskId": task_id, "workerId": body.worker_id}
        if body.run_id and body.run_id != task.run_id:
            raise ErrBadRequest()
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
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
        if domain == "ai":
            standalone = StandaloneWorkerService(self.repository.session)
            if await standalone.is_standalone(task):
                return await standalone.complete(task, body)
            direct = DirectStageWorkerService(self.repository.session)
            if await direct.is_direct(task):
                return await direct.complete(task, body)
            raise ErrNotFound()
        authority = await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if domain in {"api", "ui"} and task.status in RUN_TERMINAL_STATUSES:
            # Duplicate completion after the run closed is a no-op.
            return {"taskId": task_id, "workerId": body.worker_id, "status": task.status}
        if domain == "ui":
            await self.validate_ui_artifacts(task_id, body)
        status = ensure_final_status(body.status, {"success", "failed", "error", "canceled"})
        if domain in {"api", "ui"} and task.status == "stopping":
            status = "canceled"
            body = body.model_copy(update={"status": status, "success": False})
        if domain in {"api", "ui"} and status == "canceled":
            from testing_agent.services.test_run_stop import finish_stopped_items

            await finish_stopped_items(self.repository.session, task)
        await apply_event_to_task(task, body, status)
        await complete_domain_run(self.repository.session, domain, task, body)
        if domain == "api":
            task.error_message = redact(
                task.error_message, private_payload(authority.run).get("secrets", [])
            )
        if domain == "ui":
            # 私密变量的取值在运行记录里加密保存，错误信息里出现时同样打码。
            task.error_message = redact(
                task.error_message, private_payload(authority.run).get("secrets", [])
            )
        await self.repository.commit()
        await notify_run_changed(domain, task.run_id)
        if domain in {"api", "ui"} and getattr(authority.run, "trigger_type", "") == "live_debug":
            if domain == "api":
                from testing_agent.services.live_debug_cleanup import finish_api_debug

                await finish_api_debug(self.repository.session, task_id)
            else:
                from testing_agent.services.live_debug_cleanup import schedule_ui_debug_delivery

                await notify_ui_debug_execution_finished(task.run_id, status)
                schedule_ui_debug_delivery(task_id)
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
        await notify_run_changed("api", task.run_id)
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
        await notify_run_changed("api", task.run_id)
        return {"taskId": task_id, "itemId": item_id, "status": status}

    async def update_ui_steps(
        self, task_id: str, item_id: str | None, body: WorkerTaskEventRequest
    ) -> dict:
        """Persist a current step snapshot only for the active, authorized UI task."""
        task = await find_task(self.repository.session, "ui", task_id)
        if task.status in RUN_CLOSED_STATUSES:
            # Stop/completion already closed the run; a late progress frame must
            # not reopen a step or replace the canceled snapshot.
            return {"taskId": task_id}
        authority = await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if body.step_results is None or len(body.step_results) > 10000:
            raise ErrBadRequest()
        await self.validate_ui_artifacts(task_id, body)
        step_results = redact(body.step_results, private_payload(authority.run).get("secrets", []))
        if item_id is None:
            if task.task_type != "case_debug":
                raise ErrBadRequest()
            run = await self.repository.get_ui_case_run(task.run_id)
            if run is None:
                raise ErrNotFound()
            run.step_results_json = step_results
        else:
            if task.task_type != "suite_run":
                raise ErrBadRequest()
            item = await self.repository.get_ui_item(item_id)
            if item is None:
                raise ErrNotFound()
            if item.suite_run_id != task.run_id or item.status != "running":
                raise ErrBadRequest()
            item.step_results_json = step_results
        await self.repository.commit()
        await notify_run_changed("ui", task.run_id)
        return {"taskId": task_id}

    async def start_ui_suite_item(
        self, task_id: str, item_id: str, body: WorkerTaskEventRequest
    ) -> dict:
        task = await find_task(self.repository.session, "ui", task_id)
        await authorize_execution(self.repository.session, task)
        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        await ui_domain.start_item(self.repository, task, item_id, body)
        await self.repository.commit()
        await notify_run_changed("ui", task.run_id)
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
        await notify_run_changed("ui", task.run_id)
        return {"taskId": task_id, "itemId": item_id, "status": status}

    async def list_project_skills(self, project_id: str) -> dict:
        rows = await self.repository.list_project_skills(project_id)
        return {
            "projectId": project_id,
            "skills": [project_skill_worker_payload(row) for row in rows],
        }

    async def ai_worker_task(self, task_id: str) -> WorkerTask:
        """Load an AI task and validate its current execution authority."""
        task = await self.repository.get_worker_task("ai", task_id)
        if task is None:
            raise ErrNotFound()
        session = getattr(self.repository, "session", None)
        standalone = StandaloneWorkerService(session) if session is not None else None
        if standalone is not None and await standalone.is_standalone(task):
            await standalone.authorize(task)
            return task
        direct = DirectStageWorkerService(session) if session is not None else None
        if direct is not None and await direct.is_direct(task):
            await direct.authorize(task)
            return task
        raise ErrNotFound()

    async def llm_credentials(self, task_id: str) -> dict:
        task = await find_task(self.repository.session, "ai", task_id)
        standalone = StandaloneWorkerService(self.repository.session)
        if await standalone.is_standalone(task):
            standalone_authority = await standalone.authorize(task)
            snapshot = standalone_authority.dispatched_attempt.input_snapshot_json or {}
            connection = await require_personal_connection(
                self.repository.session,
                standalone_authority.actor_id,
                "llm",
                str(snapshot.get("llmConnectionId") or ""),
                standalone_authority.task.project_id,
            )
            payload = llm_credentials_payload(task_id, connection, self.credential_cipher)
            if not str(payload.get("apiKey") or "").strip():
                await standalone.retire(task, "操作人的模型授权已失效，请重新配置")
                await self.repository.commit()
                raise ErrForbidden()
            return payload
        direct = DirectStageWorkerService(self.repository.session)
        if await direct.is_direct(task):
            authority = await direct.authorize(task)
            connection = await require_personal_connection(
                self.repository.session,
                authority.actor_id,
                "llm",
                str(authority.input_snapshot.get("llmConnectionId") or ""),
                authority.task.project_id,
            )
            payload = llm_credentials_payload(task_id, connection, self.credential_cipher)
            if not str(payload.get("apiKey") or "").strip():
                await direct.fail_authorization(task)
                raise ErrForbidden()
            return payload
        raise ErrNotFound()

    async def gitlab_credentials(self, task_id: str) -> dict:
        """代码风险分析任务的 GitLab 凭据与绑定清单下发(凭据按快照复现)。

        绑定清单与 connection_id 取自任务创建时的 run 快照;access_token
        响应时解密,仅驻内存、不落盘、不入日志。
        """
        task = await find_task(self.repository.session, "ai", task_id)
        standalone = StandaloneWorkerService(self.repository.session)
        if await standalone.is_standalone(task):
            await standalone.authorize(task)
            raise ErrNotFound()
        direct = DirectStageWorkerService(self.repository.session)
        if await direct.is_direct(task):
            stage_authority = await direct.authorize(task)
            if task.task_type not in {
                "code_risk_analysis",
                "repository_profile",
                "ui_case_generate",
            }:
                raise ErrNotFound()
            source = stage_authority.input_snapshot.get("source") or {}
            bindings = source.get("bindings") or []
            if not isinstance(bindings, list):
                raise ErrForbidden()
            return await gitlab_credentials_payload(
                self.repository.session,
                task.task_id,
                stage_authority.task.project_id,
                bindings,
                self.credential_cipher,
                user_id=stage_authority.actor_id,
            )
        raise ErrNotFound()

    async def requirement_document(self, task_id: str):
        task = await self.ai_worker_task(task_id)
        session = getattr(self.repository, "session", None)
        standalone = StandaloneWorkerService(session) if session is not None else None
        if standalone is not None and await standalone.is_standalone(task):
            await standalone.authorize(task)
            # Independent runs use their frozen inline source, not a requirement file.
            raise ErrNotFound()
        direct = DirectStageWorkerService(session) if session is not None else None
        if direct is not None and await direct.is_direct(task):
            authority = await direct.authorize(task)
            if task.task_type not in {
                "requirement_analysis",
                "functional_case_generate",
                "ui_case_generate",
                "code_risk_analysis",
            }:
                raise ErrNotFound()
            requirement = await self.repository.get_requirement(authority.task.requirement_id)
            if requirement is None:
                raise ErrNotFound()
            source = authority.input_snapshot.get("source") or {}
            original_file, original_hash = source.get("documentFileId"), source.get("documentHash")
            if task.task_type == "requirement_analysis" and source.get("workflowVersion") == 2:
                if (original_file and original_file != requirement.document_file_id) or (
                    original_hash and original_hash != requirement.document_hash
                ):
                    from testing_agent.core.errors import AppError

                    raise AppError(409, "原始需求文件已变更，请发起新运行；历史产物仍保留", 409)
            if not getattr(requirement, "document_file_id", ""):
                from testing_agent.core.errors import ErrRequirementFileMissing

                raise ErrRequirementFileMissing()
            return requirement
        raise ErrNotFound()

    async def progress(self, task_id: str, body: WorkerProgressRequest) -> dict:
        task = await find_task(self.repository.session, "ai", task_id)
        standalone = StandaloneWorkerService(self.repository.session)
        if await standalone.is_standalone(task):
            return await standalone.progress(task, body)
        direct = DirectStageWorkerService(self.repository.session)
        if await direct.is_direct(task):
            return await direct.progress(task, body)
        raise ErrNotFound()
