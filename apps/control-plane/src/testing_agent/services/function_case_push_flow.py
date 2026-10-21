"""Local permission/intent transaction, one remote write, then durable receipt.

All SQL here belongs to the project-first current-state write fence. No network
call runs inside that transaction; the journal never commits on its own.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.domain.function_case_export import FunctionCaseExportSource, case_payload
from testing_agent.domain.integration_execution import digest
from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
)
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.user import User
from testing_agent.repositories.function_case_push import FunctionCasePushRepository
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.services.function_case_access import FunctionCaseAccess
from testing_agent.services.function_case_push_journal import CasePushJournal, CaseWriteIntent
from testing_agent.services.integration_runtime import require_runtime, restored_runtime
from testing_agent.services.mcp_client import McpCallError
from testing_agent.services.personal_credentials import PersonalCredentialAccess
from testing_agent.services.project_access import require_project_id
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_case_gateway import ZentaoCaseGateway, content_matches
from testing_agent.services.zentao_mcp import ZentaoMcpConnection


@dataclass(frozen=True)
class CasePushScope:
    project_id: str
    suite_id: str
    requirement_id: str
    sprint_id: str
    connection: ZentaoMcpConnection
    target: dict[str, int]


def export_payload(case: FunctionTestCase, target: dict[str, int]) -> dict[str, Any]:
    return dict(
        case_payload(
            FunctionCaseExportSource(
                case_id=case.case_id,
                title=case.title,
                preconditions=case.preconditions,
                steps=case.steps,
                expected_results=case.expected_results,
                priority=case.priority,
                content_json=case.content_json,
            ),
            module_id=target["module"],
            story_id=target["story"],
        )
    )


def operation_response(operation: FunctionCasePushOperation) -> dict[str, Any]:
    status = operation.status
    if status == "prepared":
        status = (
            "uncertain"
            if operation.deadline.replace(tzinfo=UTC) <= datetime.now(UTC)
            else "pending"
        )
    return {
        "caseId": operation.case_id,
        "operationId": operation.operation_id,
        "status": {"succeeded": "success", "unknown": "uncertain"}.get(status, status),
        "remoteCaseId": operation.result_json.get("remoteCaseId")
        or operation.target_json.get("remoteCaseId")
        or 0,
        "errorMessage": "写入结果待核对，不能重新推送" if operation.active_key else None,
    }


class FunctionCasePushFlow:
    def __init__(
        self,
        repository: FunctionTestCaseRepository,
        credentials: PersonalCredentialAccess,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.session = repository.session
        self.access = FunctionCaseAccess(repository)
        self.journal_repository = FunctionCasePushRepository(self.session)
        self.journal = CasePushJournal(self.journal_repository)
        self.credentials = credentials
        self.settings = settings

    async def guard(
        self,
        actor: str,
        scope: CasePushScope,
        case_id: str,
        payload: dict[str, Any],
        *,
        check_content: bool = True,
        restore_confirmed: bool = False,
    ) -> tuple[str, str]:
        """Refresh current authority, target and asset under the project's write lock."""
        project = await self.session.scalar(
            select(Project)
            .where(Project.project_id == scope.project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None:
            raise ErrNotFound()
        await require_runtime(self.session, self.settings)
        runtime = await restored_runtime(self.session)
        restore_id = runtime.restore_id if runtime is not None else ""
        reviewers = (
            await self.journal_repository.restore_reviewers(
                scope.project_id, instance_key(scope.connection.base_url), restore_id, [case_id]
            )
            if restore_id
            else {}
        )
        reviewer = reviewers.get(case_id, "")
        if restore_id and not reviewer:
            if not restore_confirmed or project.user_id != actor:
                raise AppError(409, "恢复后的用例推送须由项目所有者确认远端核对", 409)
            reviewer = actor
        _, requirement, sprint, current_project = await self.access.get_accessible_suite_context(
            actor, scope.suite_id, action="execute"
        )
        if (requirement.requirement_id, sprint.sprint_id, current_project.project_id) != (
            scope.requirement_id,
            scope.sprint_id,
            scope.project_id,
        ):
            raise AppError(409, "用例归属已变化，请重新预览", 409)
        user = await self.session.scalar(
            select(User)
            .where(User.user_id == actor)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None or user.status != "active":
            raise ErrForbidden()
        connection = scope.connection
        service = await self.session.scalar(
            select(SharedService)
            .where(
                SharedService.service_id == connection.service_id,
                SharedService.project_id == scope.project_id,
                SharedService.provider == "mcp",
                SharedService.template_id == "zentao",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            service is None
            or service.base_url != connection.endpoint
            or instance_key(service.zentao_instance_url) != instance_key(connection.base_url)
        ):
            raise AppError(409, "禅道服务目标已变化，请重新预览", 409)
        own = await self.session.scalar(
            select(IntegrationConnection)
            .join(
                ServiceAuthorization,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(
                ServiceAuthorization.service_id == connection.service_id,
                ServiceAuthorization.user_id == actor,
                IntegrationConnection.connection_id == connection.connection_id,
                IntegrationConnection.user_id == actor,
                IntegrationConnection.project_id == scope.project_id,
                IntegrationConnection.status == "active",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            own is None
            or self.credentials.mcp_token(own, user_id=actor, project_id=scope.project_id)
            != connection.token
        ):
            raise ErrForbidden()
        for kind, local_id, remote in (
            ("project", scope.project_id, "project"),
            ("sprint", scope.sprint_id, "execution"),
            ("requirement", scope.requirement_id, "story"),
        ):
            binding = await self.session.scalar(
                select(ResourceBinding)
                .where(
                    ResourceBinding.local_resource_type == kind,
                    ResourceBinding.local_resource_id == local_id,
                    ResourceBinding.provider == "zentao",
                    ResourceBinding.status == "active",
                )
                .order_by(ResourceBinding.id)
                .limit(1)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                binding is None
                or binding.instance_key != instance_key(connection.base_url)
                or str(binding.remote_resource_id) != str(scope.target[remote])
            ):
                raise AppError(409, "禅道资源绑定已变化，请重新预览", 409)
        case = await self.session.scalar(
            select(FunctionTestCase)
            .where(FunctionTestCase.case_id == case_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if case is None or case.suite_id != scope.suite_id:
            raise ErrNotFound()
        if check_content and export_payload(case, scope.target) != payload:
            raise AppError(409, "用例内容已变化，请重新预览", 409)
        return restore_id, reviewer

    async def push_one(
        self,
        actor: str,
        scope: CasePushScope,
        gateway: ZentaoCaseGateway,
        *,
        case_id: str,
        payload: dict[str, Any],
        request_id: str,
        request_fingerprint: str,
        choice: int | None,
        restore_confirmed: bool = False,
        expected_payload_digest: str | None = None,
    ) -> dict[str, Any]:
        """choice: 0 explicitly creates; positive binds; None requires an unambiguous new title."""
        try:
            key = instance_key(scope.connection.base_url)
            existing = await self.journal_repository.by_request(actor, request_id, case_id)
            if existing is not None:
                # Replays still require current access and belong to the original actor.
                await self.access.get_accessible_suite(actor, scope.suite_id, action="execute")
                if (
                    existing.request_digest != request_fingerprint
                    or existing.project_id != scope.project_id
                ):
                    raise AppError(409, "相同请求编号对应不同推送操作", 409)
                response = operation_response(existing)
                await self.session.rollback()
                return response
            if expected_payload_digest is not None and digest(payload) != expected_payload_digest:
                raise AppError(409, "原批次中尚未推送的用例内容已变化，请重新预览并提交", 409)
            pending = await self.journal_repository.active(digest([key, case_id]))
            if pending is not None:
                await self.access.get_accessible_entity(actor, case_id, action="execute")
                if pending.project_id != scope.project_id:
                    raise ErrNotFound()
                response = operation_response(pending)
                await self.session.rollback()
                return response
            identity = await self.journal_repository.identity(key, case_id)
            identifier = identity.remote_case_id if identity else None
            stored_target = dict(identity.target_json) if identity else None
            await self.session.rollback()
            target = {k: v for k, v in scope.target.items() if k != "module"}
            if stored_target is not None and stored_target != target:
                raise AppError(409, "已有映射的目标不同，请先核对映射", 409)
            if identifier is not None:
                if choice is not None and choice != identifier:
                    raise AppError(409, "用例已有稳定映射，不能通过标题选择覆盖映射", 409)
            elif choice:
                identifier = choice
            elif choice is None:
                matches = [
                    item
                    for item in (await gateway.catalog(target["execution"])).values()
                    if str(item.get("title") or "").strip() == payload["title"].strip()
                ]
                if matches:
                    raise AppError(409, "发现同名远端用例，请明确选择绑定或新建", 409)
            if identifier is not None:
                await gateway.verify_target(identifier, target)
            try:
                restore_id, restore_reviewer = await self.guard(
                    actor, scope, case_id, payload, restore_confirmed=restore_confirmed
                )
                permit = await self.journal.reserve(
                    CaseWriteIntent(
                        project_id=scope.project_id,
                        case_id=case_id,
                        instance_key=key,
                        actor=actor,
                        request_id=request_id,
                        target=target,
                        payload=payload,
                        remote_case_id=identifier,
                        request_fingerprint=request_fingerprint,
                        restore_id=restore_id,
                        restore_reviewer=restore_reviewer,
                    )
                )
                operation_id = permit.operation.operation_id
                response = operation_response(permit.operation)
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                raise AppError(409, "用例映射或推送正在被其他操作占用，请刷新核对", 409) from None
            if not permit.allowed:
                return response
            # No database transaction or connection is held while the remote call executes.
            status: Literal["succeeded", "failed", "unknown"] = "succeeded"
            error_code = ""
            received = None
            try:
                received = await gateway.write(payload, target, identifier)
            except McpCallError as exc:
                status = "unknown" if exc.uncertain else "failed"
                error_code = "remote_uncertain" if exc.uncertain else "remote_rejected"
            # Cancellation or unclassified failure leaves prepared durable and blocks all retries.
            await self.session.scalar(
                select(Project).where(Project.project_id == scope.project_id).with_for_update()
            )
            operation = await self.journal.record(
                operation_id, status, remote_case_id=received, error_code=error_code
            )
            response = operation_response(operation)
            await self.session.commit()
            return response
        except BaseException:
            await self.session.rollback()
            raise

    async def preview(
        self,
        actor: str,
        scope: CasePushScope,
        gateway: ZentaoCaseGateway,
        cases: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        _, _, _, project = await self.access.get_accessible_suite_context(
            actor, scope.suite_id, action="execute"
        )
        owner = project.user_id == actor
        identities = await self.journal_repository.identities_for(
            scope.project_id, instance_key(scope.connection.base_url), list(cases)
        )
        mapped = {row.case_id: row.remote_case_id for row in identities}
        operations = await self.journal_repository.pending_for(scope.project_id, list(cases))
        pending = {row.case_id: operation_response(row) for row in operations}
        runtime = await restored_runtime(self.session)
        reviewers = (
            await self.journal_repository.restore_reviewers(
                scope.project_id,
                instance_key(scope.connection.base_url),
                runtime.restore_id,
                list(cases),
            )
            if runtime
            else {}
        )
        restore_required = runtime is not None and any(
            case_id not in reviewers for case_id in cases
        )
        await self.session.rollback()
        catalog = (
            await gateway.catalog(scope.target["execution"])
            if any(not mapped.get(key) for key in cases)
            else {}
        )
        return {
            "restoreRequired": restore_required,
            "canConfirmNotApplied": owner,
            "items": [
                {
                    "caseId": case_id,
                    "title": payload["title"],
                    "mappedRemoteCaseId": mapped.get(case_id),
                    "operation": pending.get(case_id),
                    "candidates": [
                        {"id": identifier, "title": item.get("title", "")}
                        for identifier, item in catalog.items()
                        if str(item.get("title") or "").strip() == payload["title"].strip()
                    ],
                }
                for case_id, payload in cases.items()
            ],
        }

    async def status(self, actor: str, operation_id: str) -> dict[str, Any]:
        operation = await self.journal_repository.operation(operation_id, lock=False)
        if operation is None:
            raise ErrNotFound()
        await require_project_id(self.session, actor, operation.project_id, "read")
        response = operation_response(operation)
        await self.session.rollback()
        return response

    async def reconcile(
        self,
        actor: str,
        scope: CasePushScope,
        gateway: ZentaoCaseGateway,
        operation_id: str,
        remote_case_id: int,
    ) -> dict[str, Any]:
        """A read-only remote match resolves the original write, never starts a replacement."""
        try:
            operation = await self.journal_repository.operation(operation_id, lock=False)
            if operation is None or operation.project_id != scope.project_id:
                raise ErrNotFound()
            await self.access.get_accessible_suite(actor, scope.suite_id, action="execute")
            if not operation.active_key:
                return await self.status(actor, operation_id)
            if operation.deadline.replace(tzinfo=UTC) > datetime.now(UTC):
                raise AppError(409, "原写入仍可能在途，请等待核对窗口", 409)
            snapshot = digest([operation.status, operation.result_json, operation.request_digest])
            payload, case_id = dict(operation.payload_json), operation.case_id
            frozen_target = dict(operation.target_json)
            old_remote_id = frozen_target.pop("remoteCaseId", None)
            frozen_target.pop("_restoreId", None)
            frozen_target.pop("_restoreConfirmedBy", None)
            if old_remote_id is not None and old_remote_id != remote_case_id:
                raise AppError(409, "必须核对原操作的远端用例", 409)
            if frozen_target != {k: v for k, v in scope.target.items() if k != "module"}:
                raise AppError(409, "当前目标与原写入目标不同，不能确认回执", 409)
            await self.session.rollback()
            detail = await gateway.verify_target(remote_case_id, frozen_target)
            if not content_matches(detail, payload):
                raise AppError(409, "远端内容与原操作不一致，继续保持未决", 409)
            await self.guard(
                actor, scope, case_id, payload, check_content=False, restore_confirmed=True
            )
            current = await self.journal_repository.operation(operation_id)
            if (
                current is None
                or digest([current.status, current.result_json, current.request_digest]) != snapshot
            ):
                raise AppError(409, "核对期间原操作已变化，请刷新", 409)
            confirmed = await self.journal.record(
                operation_id, "succeeded", remote_case_id=remote_case_id, reconciled_by=actor
            )
            response = operation_response(confirmed)
            await self.session.commit()
            return response
        except IntegrityError:
            await self.session.rollback()
            raise AppError(409, "远端用例已经关联其他平台用例", 409) from None
        except BaseException:
            await self.session.rollback()
            raise

    async def confirm_not_applied(
        self,
        actor: str,
        scope: CasePushScope,
        gateway: ZentaoCaseGateway,
        operation_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """An explicit owner decision, not an inference that absence proves non-execution."""
        if not 8 <= len(reason.strip()) <= 1000:
            raise AppError(400, "请填写 8 至 1000 字的人工核对理由", 400)
        try:
            operation = await self.journal_repository.operation(operation_id, lock=False)
            if operation is None or operation.project_id != scope.project_id:
                raise ErrNotFound()
            project = await require_project_id(self.session, actor, scope.project_id, "manage")
            if project.user_id != actor:
                raise ErrForbidden()
            if not operation.active_key:
                return await self.status(actor, operation_id)
            if operation.deadline.replace(tzinfo=UTC) > datetime.now(UTC):
                raise AppError(409, "原写入仍可能在途，请等待核对窗口", 409)
            snapshot = digest([operation.status, operation.result_json, operation.request_digest])
            payload, case_id = dict(operation.payload_json), operation.case_id
            target = dict(operation.target_json)
            identifier = target.pop("remoteCaseId", None)
            target.pop("_restoreId", None)
            target.pop("_restoreConfirmedBy", None)
            if target != {k: v for k, v in scope.target.items() if k != "module"}:
                raise AppError(409, "当前目标与原写入目标不同，不能解除未决操作", 409)
            await self.session.rollback()
            evidence = {}
            if identifier is not None:
                evidence[identifier] = await gateway.verify_target(identifier, target)
            else:
                catalog = await gateway.catalog(target["execution"])
                for candidate, item in catalog.items():
                    if str(item.get("title") or "").strip() == payload["title"].strip():
                        evidence[candidate] = await gateway.detail(candidate, fresh=True)
            if any(content_matches(item, payload) for item in evidence.values()):
                raise AppError(409, "发现与原写入内容一致的远端用例，请确认已有结果", 409)
            evidence_digest = digest(evidence)
            await self.guard(
                actor, scope, case_id, payload, check_content=False, restore_confirmed=True
            )
            current_project = await self.session.scalar(
                select(Project).where(Project.project_id == scope.project_id).with_for_update()
            )
            if current_project is None or current_project.user_id != actor:
                raise ErrForbidden()
            current = await self.journal_repository.operation(operation_id)
            if (
                current is None
                or digest([current.status, current.result_json, current.request_digest]) != snapshot
            ):
                raise AppError(409, "核对期间原操作已变化，请刷新", 409)
            confirmed = await self.journal.record(
                operation_id,
                "failed",
                error_code="owner_confirmed_not_applied",
                reconciled_by=actor,
                reconciliation_note=reason.strip(),
                evidence_digest=evidence_digest,
            )
            response = operation_response(confirmed)
            await self.session.commit()
            return response
        except BaseException:
            await self.session.rollback()
            raise

    async def admit(
        self,
        actor: str,
        scope: CasePushScope,
        request_id: str,
        fingerprint: str,
        manifest: dict[str, dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        """Freeze one actor/request across all cases, even when a retry has disjoint IDs."""
        from testing_agent.models.function_case_push import FunctionCasePushRequest

        try:
            await self.session.scalar(
                select(Project).where(Project.project_id == scope.project_id).with_for_update()
            )
            await self.access.get_accessible_suite(actor, scope.suite_id, action="execute")
            target_digest = digest([instance_key(scope.connection.base_url), scope.target])
            existing = await self.journal_repository.request(actor, request_id, lock=True)
            if existing is not None:
                if (
                    existing.project_id != scope.project_id
                    or existing.request_digest != fingerprint
                    or existing.target_digest != target_digest
                ):
                    raise AppError(409, "相同请求编号对应不同批次或目标，请使用新的提交编号", 409)
                result = dict(existing.manifest_json)
            else:
                result = manifest
                self.session.add(
                    FunctionCasePushRequest(
                        actor_user_id=actor,
                        request_id=request_id,
                        project_id=scope.project_id,
                        request_digest=fingerprint,
                        target_digest=target_digest,
                        manifest_json=manifest,
                    )
                )
            await self.session.commit()
            return result
        except IntegrityError:
            await self.session.rollback()
            raise AppError(409, "相同提交编号正在使用，请用原参数重试", 409) from None
        except BaseException:
            await self.session.rollback()
            raise

    async def frozen_selection(
        self, actor: str, request_id: str, fingerprint: str
    ) -> set[str] | None:

        batch = await self.journal_repository.request(actor, request_id)
        if batch is None:
            return None
        if batch.request_digest != fingerprint:
            raise AppError(409, "相同请求编号对应不同批次，请使用新的提交编号", 409)
        return set(batch.manifest_json)
