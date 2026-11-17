from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select

from testing_agent.core.enums import (
    PERF_RUN_CLOSED_STATUSES,
    PerfRunStatus,
)
from testing_agent.core.errors import (
    AppError,
    ErrBadRequest,
    ErrForbidden,
    ErrPerfCaseDisabled,
    ErrPerfCaseNotFound,
    ErrPerfDataFileMissing,
    ErrPerfRunEnvironmentMismatch,
    ErrPerfRunNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.project_policy import ProjectAction
from testing_agent.models.monitoring_connection import MonitoringConnection
from testing_agent.models.perf_case import PerfCase
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.repositories.monitoring_connection import MonitoringConnectionRepository
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.repositories.perf_run import PerfRunRepository
from testing_agent.schemas.perf_run import (
    PerfRunCreate,
    PerfRunMonitoringSnapshot,
    PerfRunResponse,
    PerfRunSummaryResponse,
)
from testing_agent.schemas.perf_suite_run import PerfSuiteRunCreate
from testing_agent.services.api_request_render import render_template_string
from testing_agent.services.environment_access import authorized_environment_vars
from testing_agent.services.execution_secrets import redact
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.monitoring_connection import MonitoringConnectionService
from testing_agent.services.perf_case_spec import parse_case_yaml
from testing_agent.services.project_access import require_project_id
from testing_agent.services.stored_file import StoredFileService

PERF_MAX_DURATION_SECONDS = 3600
PERF_STOP_GRACE_SECONDS = 30
PERF_PUSH_INTERVAL = "1s"
PERF_TREND_STATS = "p(95),p(99),avg,min,max"

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_ENV_NAMES = {
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PWD",
    "PYTHONHOME",
    "PYTHONPATH",
    "SHELL",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USER",
    "baseUrl",
}


class PerfRunService:
    def __init__(
        self,
        repository: PerfRunRepository,
        *,
        cases: PerfCaseRepository,
        environments: ApiEnvironmentRepository,
        monitoring: MonitoringConnectionRepository,
        monitoring_service: MonitoringConnectionService,
        files: StoredFileService,
        credential_cipher: IntegrationCredentialCipher,
    ) -> None:
        self.repository = repository
        self.cases = cases
        self.environments = environments
        self.monitoring = monitoring
        self.monitoring_service = monitoring_service
        self.files = files
        self.credential_cipher = credential_cipher

    async def _accessible_run(self, user_id: str, run_id: str, *, action: ProjectAction) -> PerfRun:
        run = await self.repository.get_run(run_id, for_update=action == "execute")
        if run is None:
            raise ErrPerfRunNotFound()
        await require_project_id(self.repository.session, user_id, run.project_id, action=action)
        return run

    def _validate_base_url(self, value: str) -> str:
        if "{{" in value or "}}" in value:
            raise AppError(400, "环境 baseUrl 存在未解析变量", 400)
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise AppError(400, "环境 baseUrl 必须是 http(s) URL", 400)
        if parts.username or parts.password:
            raise AppError(400, "环境 baseUrl 不能包含用户名或密码", 400)
        if parts.query or parts.fragment:
            raise AppError(400, "环境 baseUrl 不能包含查询或片段", 400)
        return value.rstrip("/")

    def _validate_variables(self, variables: dict[str, str]) -> None:
        for name, value in variables.items():
            if not _ENV_NAME_RE.fullmatch(name):
                raise AppError(400, f"环境变量名不合法: {name}", 400)
            if name.startswith("K6_") or name in _RESERVED_ENV_NAMES:
                raise AppError(400, f"环境变量名保留，不能用于性能测试: {name}", 400)
            if not isinstance(value, str):
                raise AppError(400, f"环境变量 {name} 的值必须是字符串", 400)

    def _auth_secrets(self, auth: dict[str, Any]) -> list[str]:
        auth_type = auth.get("type")
        if auth_type == "basic":
            return [str(auth.get("password") or "")]
        if auth_type == "bearer":
            return [str(auth.get("token") or "")]
        if auth_type == "headers":
            return [str(value) for value in (auth.get("headers") or {}).values()]
        return []

    def _public_auth(self, auth: dict[str, Any]) -> dict[str, Any]:
        auth_type = auth.get("type", "none")
        if auth_type == "basic":
            return {"type": "basic", "username": auth.get("username", "")}
        if auth_type == "headers":
            return {
                "type": "headers",
                "headers": {name: "" for name in (auth.get("headers") or {})},
            }
        return {"type": auth_type}

    def _monitoring_snapshot(self, connection: MonitoringConnection) -> dict[str, Any]:
        return {
            "connectionId": connection.connection_id,
            "name": connection.name,
            "remoteWriteUrl": connection.remote_write_url,
        }

    async def _data_files(self, case: PerfCase) -> list[dict[str, Any]]:
        metadata = case.data_files_json or []
        rows = []
        for item in metadata:
            file_id = item.get("fileId") if isinstance(item, dict) else None
            if not file_id:
                raise ErrPerfDataFileMissing()
            try:
                row = await self.files.get(str(file_id))
            except AppError as exc:
                raise ErrPerfDataFileMissing() from exc
            if (
                row.status != "attached"
                or row.purpose != "perf_case_data"
                or row.resource_type != "perf_case"
                or row.resource_id != case.case_id
                or row.project_id != case.project_id
                or row.filename != item.get("filename")
                or row.size != item.get("size")
                or row.sha256 != item.get("sha256")
            ):
                raise ErrPerfDataFileMissing()
            rows.append(item)
        return rows

    async def _build_spec(
        self,
        user_id: str,
        case: PerfCase,
        body: PerfRunCreate | PerfSuiteRunCreate,
        run_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str, list[str], list[dict[str, Any]]]:
        if not case.enabled:
            raise ErrPerfCaseDisabled()
        parsed = parse_case_yaml(case.yaml)
        environment = await self.environments.get_environment(body.environment_id)
        if environment is None or environment.project_id != case.project_id:
            raise ErrPerfRunEnvironmentMismatch()
        if environment.kind != "perf":
            raise ErrPerfRunEnvironmentMismatch()
        connection = await self.monitoring.get_connection(body.monitoring_connection_id)
        if connection is None or connection.project_id != case.project_id:
            raise ErrPerfRunEnvironmentMismatch()
        self.monitoring_service.require_enabled(connection)
        env_rows = await authorized_environment_vars(
            self.repository.session, user_id, environment.environment_id
        )
        variables = {row.var_key: row.value for row in env_rows}
        self._validate_variables(variables)
        base_url = self._validate_base_url(render_template_string(environment.base_url, variables))
        data_files = await self._data_files(case)
        remote_auth = self.monitoring_service.remote_write_auth(connection)
        case_spec = parsed["case"]
        spec = {
            "specVersion": "1.0",
            "runId": run_id,
            "projectId": case.project_id,
            "case": case_spec,
            "environment": {"baseUrl": base_url, "variables": variables},
            "remoteWrite": {
                "url": connection.remote_write_url,
                "auth": remote_auth,
                "pushInterval": PERF_PUSH_INTERVAL,
                "trendStats": PERF_TREND_STATS,
            },
            "limits": {
                "maxDurationSeconds": PERF_MAX_DURATION_SECONDS,
                "stopGraceSeconds": PERF_STOP_GRACE_SECONDS,
            },
        }
        secrets = [row.value for row in env_rows if row.is_secret]
        secrets.extend(self._auth_secrets(remote_auth))
        public_spec = copy.deepcopy(spec)
        for row in env_rows:
            if row.is_secret:
                public_spec["environment"]["variables"][row.var_key] = "********"
        public_spec["remoteWrite"]["auth"] = self._public_auth(remote_auth)
        public_spec = redact(public_spec, secrets)
        private_payload = self.credential_cipher.encrypt(
            json.dumps({"spec": spec, "secrets": secrets}, ensure_ascii=False)
        )
        return public_spec, spec, private_payload, secrets, data_files

    def _summary(self, run: PerfRun) -> dict[str, Any]:
        response = PerfRunSummaryResponse(
            run_id=run.run_id,
            case_id=run.case_id,
            project_id=run.project_id,
            case_version=run.case_version,
            case_name=run.case_name,
            environment_id=run.environment_id,
            environment_name=run.environment_name,
            monitoring_connection_id=run.monitoring_connection_id,
            monitoring_connection_name=run.monitoring_connection_name,
            trigger_user_id=run.trigger_user_id,
            trigger_type=run.trigger_type,
            status=run.status,
            outcome=run.outcome,
            flags=run.flags_json or [],
            error_message=run.error_message,
            k6_version=run.k6_version,
            template_version=run.template_version,
            script_sha256=run.script_sha256,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            created_at=run.created_at,
        )
        return response.model_dump(by_alias=True, mode="json")

    def _detail(self, run: PerfRun) -> dict[str, Any]:
        response = PerfRunResponse(
            run_id=run.run_id,
            case_id=run.case_id,
            project_id=run.project_id,
            case_version=run.case_version,
            case_name=run.case_name,
            environment_id=run.environment_id,
            environment_name=run.environment_name,
            monitoring_connection_id=run.monitoring_connection_id,
            monitoring_connection_name=run.monitoring_connection_name,
            trigger_user_id=run.trigger_user_id,
            trigger_type=run.trigger_type,
            status=run.status,
            outcome=run.outcome,
            flags=run.flags_json or [],
            error_message=run.error_message,
            k6_version=run.k6_version,
            template_version=run.template_version,
            script_sha256=run.script_sha256,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            created_at=run.created_at,
            summary=run.summary_json,
            log_tail=run.log_tail,
            runner=run.runner_json,
            data_files=run.data_files_json or [],
            monitoring=(
                PerfRunMonitoringSnapshot.model_validate(run.monitoring_snapshot_json)
                if run.monitoring_snapshot_json is not None
                else None
            ),
        )
        return response.model_dump(by_alias=True, mode="json")

    async def prepare(
        self,
        user_id: str,
        case: PerfCase,
        body: PerfRunCreate | PerfSuiteRunCreate,
        run_id: str,
    ) -> PerfRun:
        """Freeze one case run without queueing its Worker task."""
        public_spec, _spec, private_payload, _secrets, data_files = await self._build_spec(
            user_id, case, body, run_id
        )
        environment = await self.environments.get_environment(body.environment_id)
        connection = await self.monitoring.get_connection(body.monitoring_connection_id)
        if environment is None or connection is None:
            raise ErrPerfRunEnvironmentMismatch()
        return PerfRun(
            run_id=run_id,
            case_id=case.case_id,
            project_id=case.project_id,
            case_version=case.version,
            case_name=case.name,
            environment_id=environment.environment_id,
            environment_name=environment.name,
            monitoring_connection_id=connection.connection_id,
            monitoring_connection_name=connection.name,
            monitoring_snapshot_json=self._monitoring_snapshot(connection),
            trigger_user_id=user_id,
            trigger_type="manual",
            status=PerfRunStatus.QUEUED.value,
            case_yaml=case.yaml,
            spec_json=public_spec,
            data_files_json=data_files,
            private_payload=private_payload,
        )

    def enqueue(self, run_id: str) -> WorkerTask:
        task = WorkerTask(
            domain="perf",
            task_id=new_id(),
            task_type="perf_run",
            run_id=run_id,
            status="pending",
        )
        self.repository.session.add(task)
        return task

    async def create(self, user_id: str, case_id: str, body: PerfRunCreate) -> dict[str, Any]:
        case = await self.cases.get_case(case_id)
        if case is None:
            raise ErrPerfCaseNotFound()
        await require_project_id(
            self.repository.session, user_id, case.project_id, action="execute"
        )
        run = await self.prepare(user_id, case, body, new_id())
        self.repository.add(run)
        self.enqueue(run.run_id)
        await self.repository.commit()
        await self.repository.refresh(run)
        return self._detail(run)

    async def list_runs(
        self,
        user_id: str,
        project_id: str,
        *,
        case_id: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        if status and status not in {item.value for item in PerfRunStatus}:
            raise ErrBadRequest()
        rows, total = await self.repository.list_by_project(
            project_id,
            case_id=case_id,
            status=status,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
        )
        return {"total": total, "items": [self._summary(row) for row in rows]}

    async def get(self, user_id: str, run_id: str) -> dict[str, Any]:
        return self._detail(await self._accessible_run(user_id, run_id, action="read"))

    def private_spec(self, run: PerfRun) -> tuple[dict[str, Any], list[str]]:
        return read_private_spec(run, self.credential_cipher)

    async def stop(self, user_id: str, run_id: str) -> dict[str, Any]:
        from testing_agent.services.perf_suite_run import (
            on_child_completed_after_commit,
            stop_suite_for_child,
        )

        probe = await self.repository.get_run(run_id)
        if probe is None:
            raise ErrPerfRunNotFound()
        await require_project_id(
            self.repository.session, user_id, probe.project_id, action="execute"
        )
        if probe.trigger_user_id != user_id:
            raise ErrForbidden()
        if probe.status in PERF_RUN_CLOSED_STATUSES:
            return {"status": probe.status}
        # Lock the suite before its child run so suite-level and child-level stops
        # always acquire parent/child rows in the same order.
        await stop_suite_for_child(self.repository.session, run_id)
        run = await self.repository.get_run(run_id, for_update=True)
        if run is None:
            raise ErrPerfRunNotFound()
        task = await self.repository.session.scalar(
            select(WorkerTask)
            .where(WorkerTask.domain == "perf", WorkerTask.run_id == run_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if run.status == PerfRunStatus.QUEUED.value and (
            task is None or task.status in {"pending"}
        ):
            run.status = PerfRunStatus.CANCELED.value
            run.finished_at = now
            run.error_message = "用户已停止运行"
            if task is not None:
                task.status = "canceled"
                task.finished_at = now
                task.error_message = "用户已停止运行"
        else:
            run.status = PerfRunStatus.STOPPING.value
            if task is not None:
                task.status = "stopping"
        await self.repository.commit()
        if run.status == PerfRunStatus.CANCELED.value:
            await on_child_completed_after_commit(self.repository.session, run_id)
        return {"status": run.status}


def read_private_spec(
    run: PerfRun, cipher: IntegrationCredentialCipher
) -> tuple[dict[str, Any], list[str]]:
    """Decrypt the frozen RunSpec and its secret values for the current lease holder."""
    if not run.private_payload:
        raise AppError(409, "性能运行缺少冻结规格，请重新发起运行", 409)
    try:
        payload = json.loads(cipher.decrypt(run.private_payload))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(409, "性能运行冻结规格无法解密，请重新发起运行", 409) from exc
    spec = payload.get("spec") if isinstance(payload, dict) else None
    secrets = payload.get("secrets") if isinstance(payload, dict) else None
    if not isinstance(spec, dict):
        raise AppError(409, "性能运行冻结规格不合法，请重新发起运行", 409)
    return spec, [str(item) for item in (secrets or []) if item]
