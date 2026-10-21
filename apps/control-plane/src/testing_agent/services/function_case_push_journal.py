"""Durable one-write permits and receipts; no credentials, network IO or implicit commit.

The coordinator must lock the project and check current authorization before reserve,
commit the permit before sending, and never send when reserve returns allowed=False.
Receipt transactions use the same project-first lock order. Unknown permits retain
exclusivity until explicit remote verification resolves the original operation.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from testing_agent.core.errors import AppError
from testing_agent.domain.integration_execution import digest, require_safe_snapshot
from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
    FunctionCaseRemoteIdentity,
)
from testing_agent.repositories.function_case_push import FunctionCasePushRepository


def conflict(message: str) -> AppError:
    return AppError(409, message, 409)


@dataclass(frozen=True)
class CaseWriteIntent:
    project_id: str
    case_id: str
    instance_key: str
    actor: str
    request_id: str
    target: dict[str, Any]
    payload: dict[str, Any]
    # None means explicit creation; an integer is a binding verified by the coordinator.
    remote_case_id: int | None = None

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "projectId": self.project_id,
                "caseId": self.case_id,
                "instanceKey": self.instance_key,
                "target": self.target,
                "payload": self.payload,
                "remoteCaseId": self.remote_case_id,
            }
        )


@dataclass(frozen=True)
class CaseWritePermit:
    operation: FunctionCasePushOperation
    allowed: bool


class CasePushJournal:
    def __init__(self, repository: FunctionCasePushRepository) -> None:
        self.repository = repository

    async def reserve(self, intent: CaseWriteIntent) -> CaseWritePermit:
        require_safe_snapshot(intent.target)
        require_safe_snapshot(intent.payload)
        if intent.remote_case_id is not None and (
            type(intent.remote_case_id) is not int or intent.remote_case_id <= 0
        ):
            raise conflict("绑定必须提供有效远端用例编号")
        previous = await self.repository.by_request(intent.actor, intent.request_id, intent.case_id)
        if previous is not None:
            if previous.request_digest != intent.fingerprint:
                raise conflict("相同请求编号对应不同用例推送内容")
            # A persisted permit may already have been sent, even if no result was received.
            return CaseWritePermit(previous, False)
        key = digest([intent.instance_key, intent.case_id])
        if await self.repository.active(key) is not None:
            raise conflict("该用例存在未决写入，请先核对原操作")
        identity = await self.repository.identity(intent.instance_key, intent.case_id)
        if identity is None:
            identity = FunctionCaseRemoteIdentity(
                project_id=intent.project_id,
                case_id=intent.case_id,
                instance_key=intent.instance_key,
                remote_case_id=intent.remote_case_id,
                target_json=deepcopy(intent.target),
                revision=0,
            )
            self.repository.add(identity)
            await self.repository.flush()
        elif (
            identity.project_id != intent.project_id
            or identity.target_json != intent.target
            or identity.remote_case_id != intent.remote_case_id
        ):
            raise conflict("用例映射或目标已变化，请重新读取后确认")
        operation = FunctionCasePushOperation(
            operation_id=uuid4().hex,
            identity_id=identity.id,
            project_id=intent.project_id,
            case_id=intent.case_id,
            actor_user_id=intent.actor,
            request_id=intent.request_id,
            request_digest=intent.fingerprint,
            active_key=key,
            status="prepared",
            action="create" if intent.remote_case_id is None else "update",
            target_json={**deepcopy(intent.target), "remoteCaseId": intent.remote_case_id},
            payload_json=deepcopy(intent.payload),
            result_json={},
            deadline=datetime.now(UTC) + timedelta(minutes=5),
        )
        self.repository.add(operation)
        await self.repository.flush()
        return CaseWritePermit(operation, True)

    async def record(
        self,
        operation_id: str,
        status: Literal["succeeded", "failed", "unknown"],
        *,
        remote_case_id: int | None = None,
        error_code: str = "",
    ) -> FunctionCasePushOperation:
        operation = await self.repository.operation(operation_id)
        if operation is None:
            raise AppError(404, "推送操作不存在", 404)
        result = {"remoteCaseId": remote_case_id, "errorCode": error_code}
        if operation.status in {"succeeded", "failed"}:
            if operation.status != status or operation.result_json != result:
                raise conflict("原操作已有不同的终态回执")
            return operation
        if status == "succeeded":
            if isinstance(remote_case_id, bool) or not remote_case_id or remote_case_id <= 0:
                raise conflict("成功回执缺少有效远端用例编号")
            identity = await self.repository.identity_by_id(operation.identity_id)
            if identity is None or identity.remote_case_id not in (None, remote_case_id):
                raise conflict("远端回执与已有用例映射冲突")
            identity.remote_case_id = remote_case_id
            identity.revision += 1
        operation.status = status
        operation.result_json = result
        if status in {"succeeded", "failed"}:
            operation.active_key = None
        await self.repository.flush()
        return operation
