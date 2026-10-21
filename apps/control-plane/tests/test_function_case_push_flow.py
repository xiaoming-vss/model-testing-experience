from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.initial_schema_migration import (
    compile_longtext_for_sqlite as compile_longtext_for_sqlite,
)

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.models import Base
from testing_agent.models.function_case_push import FunctionCasePushOperation
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.services.function_case_push_flow import (
    CasePushScope,
    FunctionCasePushFlow,
    export_payload,
)
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.mcp_client import McpCallError
from testing_agent.services.personal_credentials import PersonalCredentialAccess
from testing_agent.services.service_instance import instance_key
from testing_agent.services.zentao_case_gateway import ZentaoCaseGateway
from testing_agent.services.zentao_mcp import ZentaoMcpConnection


@pytest_asyncio.fixture
async def prepared(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'flow.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cipher = IntegrationCredentialCipher("test-only")
    async with sessions() as session:
        session.add(User(user_id="actor", nickname="actor", status="active"))
        session.add(Project(project_id="project", user_id="actor", name="project"))
        session.add(
            Sprint(
                sprint_id="sprint",
                project_id="project",
                name="sprint",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=1),
            )
        )
        session.add(
            Requirement(requirement_id="requirement", sprint_id="sprint", name="requirement")
        )
        session.add(FunctionTestSuite(suite_id="suite", requirement_id="requirement", name="suite"))
        session.add(
            FunctionTestCase(
                case_id="case",
                suite_id="suite",
                title="title",
                steps="step",
                expected_results="expected",
            )
        )
        session.add(
            SharedService(
                service_id="service",
                project_id="project",
                provider="mcp",
                template_id="zentao",
                name="mcp",
                base_url="https://mcp.test",
                zentao_instance_url="https://zentao.test",
            )
        )
        session.add(
            IntegrationConnection(
                connection_id="connection",
                project_id="project",
                user_id="actor",
                provider="mcp",
                name="own",
                secret_json={"token": cipher.encrypt("token")},
                status="active",
            )
        )
        session.add(
            ServiceAuthorization(service_id="service", user_id="actor", connection_id="connection")
        )
        for kind, local, remote, identifier in [
            ("project", "project", "project", 11),
            ("sprint", "sprint", "execution", 22),
            ("requirement", "requirement", "story", 33),
        ]:
            session.add(
                ResourceBinding(
                    binding_id=kind,
                    user_id="actor",
                    provider="zentao",
                    connection_id="connection",
                    local_resource_type=kind,
                    local_resource_id=local,
                    remote_resource_type=remote,
                    remote_resource_id=str(identifier),
                    instance_url="https://zentao.test",
                    instance_key=instance_key("https://zentao.test"),
                )
            )
        await session.commit()
    scope = CasePushScope(
        "project",
        "suite",
        "requirement",
        "sprint",
        ZentaoMcpConnection(
            "connection", "https://zentao.test", "https://mcp.test", "token", service_id="service"
        ),
        {"productID": 1, "project": 11, "execution": 22, "story": 33, "module": 0},
    )
    yield sessions, scope, PersonalCredentialAccess(cipher)
    await engine.dispose()


class Remote:
    def __init__(self, session, sessions, *, failure="", revoke=False):
        self.session, self.sessions = session, sessions
        self.failure, self.revoke = failure, revoke
        self.rows, self.writes = {}, []

    async def call(self, name, args, **kwargs):
        assert not self.session.in_transaction(), "Network must not hold a DB transaction"
        if name == "get_executions_executionID_testcases":
            if self.revoke:
                async with self.sessions() as session:
                    row = await session.scalar(select(IntegrationConnection))
                    row.status = "invalid"
                    await session.commit()
            return {"testcases": list(self.rows.values()), "total": len(self.rows)}
        if name == "get_testcases_caseID":
            return {"testcase": self.rows[args["caseID"]]}
        async with self.sessions() as observer:
            operation = await observer.scalar(
                select(FunctionCasePushOperation).where(
                    FunctionCasePushOperation.active_key.is_not(None)
                )
            )
            assert operation is not None and operation.status == "prepared"
        self.writes.append(name)
        if self.failure:
            raise McpCallError("unknown", uncertain=True)
        identifier = args.get("testcasID", 71)
        payload = args["payload"]
        self.rows[identifier] = {
            "id": identifier,
            **payload,
            "product": 1,
            "steps": [
                {"desc": a, "expect": b}
                for a, b in zip(payload["steps"], payload["expects"], strict=True)
            ],
        }
        return {"status": "success", "id": identifier}


@pytest.mark.asyncio
async def test_real_flow_commits_before_network_and_replays_receipt(prepared):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        case = await session.scalar(select(FunctionTestCase))
        payload = export_payload(case, scope.target)
        remote = Remote(session, sessions)
        gateway = ZentaoCaseGateway(remote)
        args = dict(
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        result = await flow.push_one("actor", scope, gateway, **args)
        assert result["status"] == "success" and result["remoteCaseId"] == 71
        assert await flow.push_one("actor", scope, gateway, **args) == result
        result = await flow.push_one(
            "actor",
            scope,
            gateway,
            **{**args, "request_id": "second", "request_fingerprint": "b" * 64},
        )
        assert result["remoteCaseId"] == 71
        assert remote.writes == ["post_testcases", "put_testcases_testcasID"]


@pytest.mark.asyncio
async def test_unknown_write_blocks_new_request_across_service_restart(prepared):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions, failure="timeout")
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        result = await flow.push_one(
            "actor",
            scope,
            ZentaoCaseGateway(remote),
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        assert result["status"] == "uncertain"
    async with sessions() as session:
        remote.session = session
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        repeated = await flow.push_one(
            "actor",
            scope,
            ZentaoCaseGateway(remote),
            case_id="case",
            payload=payload,
            request_id="second",
            request_fingerprint="b" * 64,
            choice=None,
        )
        assert repeated["status"] == "uncertain"
        assert remote.writes == ["post_testcases"]


@pytest.mark.asyncio
async def test_revoked_credentials_between_remote_read_and_prepare_cannot_write(prepared):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions, revoke=True)
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        with pytest.raises(AppError) as error:
            await flow.push_one(
                "actor",
                scope,
                ZentaoCaseGateway(remote),
                case_id="case",
                payload=payload,
                request_id="first",
                request_fingerprint="a" * 64,
                choice=None,
            )
        assert error.value.http_code == 403
        assert not remote.writes
        assert await session.scalar(select(FunctionCasePushOperation)) is None


@pytest.mark.asyncio
async def test_lost_receipt_never_reexecutes_remote_write(prepared, monkeypatch):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions)
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )

        async def unavailable(*args, **kwargs):
            raise RuntimeError("receipt database unavailable")

        monkeypatch.setattr(flow.journal, "record", unavailable)
        args = dict(
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        with pytest.raises(RuntimeError):
            await flow.push_one("actor", scope, ZentaoCaseGateway(remote), **args)
        result = await flow.push_one("actor", scope, ZentaoCaseGateway(remote), **args)
        assert result["status"] == "pending"
        assert remote.writes == ["post_testcases"]


@pytest.mark.asyncio
async def test_reconciliation_checks_content_and_records_actor_without_write(prepared):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions, failure="timeout")
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        result = await flow.push_one(
            "actor",
            scope,
            ZentaoCaseGateway(remote),
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        operation_id = result["operationId"]
        operation = await session.scalar(select(FunctionCasePushOperation))
        operation.deadline = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        remote.rows[71] = {
            "id": 71,
            **payload,
            "product": 1,
            "steps": [{"desc": "wrong", "expect": "expected"}],
        }
        with pytest.raises(AppError, match="远端内容与原操作不一致"):
            await flow.reconcile("actor", scope, ZentaoCaseGateway(remote), operation_id, 71)
        remote.rows[71]["steps"] = [{"desc": "step", "expect": "expected"}]
        result = await flow.reconcile("actor", scope, ZentaoCaseGateway(remote), operation_id, 71)
        assert result["status"] == "success" and result["remoteCaseId"] == 71
        assert remote.writes == ["post_testcases"]
        operation = await session.scalar(select(FunctionCasePushOperation))
        assert operation.result_json["reconciledBy"] == "actor"
        assert operation.active_key is None


@pytest.mark.asyncio
async def test_owner_confirmation_preserves_reason_and_requires_new_request(prepared):
    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions, failure="timeout")
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        args = dict(
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        result = await flow.push_one("actor", scope, ZentaoCaseGateway(remote), **args)
        operation_id = result["operationId"]
        reason = "人工核对了目标执行中的全部用例，确认未写入"
        with pytest.raises(AppError, match="等待核对窗口"):
            await flow.confirm_not_applied(
                "actor", scope, ZentaoCaseGateway(remote), operation_id, reason
            )
        operation = await session.scalar(select(FunctionCasePushOperation))
        operation.deadline = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        result = await flow.confirm_not_applied(
            "actor", scope, ZentaoCaseGateway(remote), operation_id, reason
        )
        assert result["status"] == "failed"
        operation = await session.scalar(select(FunctionCasePushOperation))
        assert operation.result_json["note"] == reason
        assert operation.result_json["reconciledBy"] == "actor"
        assert len(operation.result_json["evidenceDigest"]) == 64
        assert (await flow.push_one("actor", scope, ZentaoCaseGateway(remote), **args))[
            "status"
        ] == "failed"
        assert remote.writes == ["post_testcases"]


@pytest.mark.asyncio
async def test_restored_database_requires_owner_review_even_after_global_release(prepared):
    from testing_agent.models.integration_job import IntegrationRuntime
    from testing_agent.services.integration_runtime import key_digest

    sessions, scope, credentials = prepared
    settings = Settings.from_mapping(
        {
            "integration_execution": {"runtime_generation": "restored"},
            "security": {"integration_worker": {"key": "restored-key"}},
        }
    )
    async with sessions() as session:
        session.add(
            IntegrationRuntime(
                id=1,
                restore_id="restore-1",
                runtime_generation="restored",
                worker_key_digest=key_digest("restored-key"),
                blocked=False,
            )
        )
        await session.commit()
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        flow = FunctionCasePushFlow(FunctionTestCaseRepository(session), credentials, settings)
        remote = Remote(session, sessions)
        preview = await flow.preview("actor", scope, ZentaoCaseGateway(remote), {"case": payload})
        assert preview["restoreRequired"]
        args = dict(
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=0,
        )
        with pytest.raises(AppError, match="恢复后的用例推送"):
            await flow.push_one("actor", scope, ZentaoCaseGateway(remote), **args)
        assert not remote.writes
        result = await flow.push_one(
            "actor", scope, ZentaoCaseGateway(remote), **args, restore_confirmed=True
        )
        assert result["status"] == "success"
        operation = await session.scalar(select(FunctionCasePushOperation))
        assert operation.target_json["_restoreId"] == "restore-1"
        assert operation.target_json["_restoreConfirmedBy"] == "actor"

        await session.rollback()
        preview = await flow.preview("actor", scope, ZentaoCaseGateway(remote), {"case": payload})
        assert not preview["restoreRequired"], (
            "Reviewed cases do not require perpetual owner-only pushes"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("super_admin", [False, True])
async def test_non_owner_cannot_clear_unknown_write_even_with_admin_access(prepared, super_admin):
    from testing_agent.models.project_member import ProjectMember

    sessions, scope, credentials = prepared
    async with sessions() as session:
        payload = export_payload(await session.scalar(select(FunctionTestCase)), scope.target)
        remote = Remote(session, sessions, failure="timeout")
        flow = FunctionCasePushFlow(
            FunctionTestCaseRepository(session), credentials, Settings.from_mapping({})
        )
        result = await flow.push_one(
            "actor",
            scope,
            ZentaoCaseGateway(remote),
            case_id="case",
            payload=payload,
            request_id="first",
            request_fingerprint="a" * 64,
            choice=None,
        )
        session.add(
            User(user_id="other", nickname="other", status="active", is_super_admin=super_admin)
        )
        session.add(ProjectMember(project_id="project", user_id="other", role="member"))
        operation = await session.scalar(select(FunctionCasePushOperation))
        operation.deadline = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(AppError) as error:
            await flow.confirm_not_applied(
                "other",
                scope,
                ZentaoCaseGateway(remote),
                result["operationId"],
                "已人工核对远端全部用例",
            )
        assert error.value.http_code == 403
        operation = await session.scalar(select(FunctionCasePushOperation))
        assert operation.status == "unknown" and operation.active_key is not None
        assert remote.writes == ["post_testcases"]
