"""Real local transactions and authorization, with a readonly MCP adapter at the seam."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.api.deps import build_integration_bug_service
from testing_agent.core.config import IntegrationExecutionSettings, Settings
from testing_agent.core.errors import AppError
from testing_agent.domain.integration_execution import digest
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.integration_job import (
    IntegrationJob,
    IntegrationJobStep,
    IntegrationRestoreReview,
    IntegrationRuntime,
)
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.schemas.integration_bug import IntegrationSyncRequest
from testing_agent.schemas.integration_job import (
    IntegrationClaimRequest,
    IntegrationPrepareRequest,
    IntegrationResultRequest,
    IntegrationWorkerIdentity,
)
from testing_agent.schemas.integration_restore import IntegrationRestoreAudit
from testing_agent.services.bug_zentao_description import source_hash
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.integration_restore import IntegrationRestoreService
from testing_agent.services.service_instance import instance_key

NOW = datetime(2026, 10, 7, tzinfo=UTC)
INSTANCE = "https://zentao.example/sub"


@compiles(LONGTEXT, "sqlite")
def longtext(type_, compiler, **kwargs):
    return "TEXT"


class Remote:
    def __init__(self):
        self.calls, self.tokens, self.on_bug = [], [], None
        self.bug = {
            "id": 50,
            "project": 10,
            "execution": 20,
            "story": 30,
            "product": 40,
            "title": "Restored",
            "steps": "<p>restored</p>",
            "openedBuild": ["trunk"],
            "assignedTo": "",
            "files": [],
        }
        self.proofs = {}
        self.file_metadata = {}

    def factory(self, endpoint, token):
        remote = self
        remote.tokens.append(token)

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def call(self, name, arguments, **kwargs):
                remote.calls.append((name, arguments))
                if name == "get_zentao_instance":
                    return {
                        "schemaVersion": 1,
                        "instanceUrl": INSTANCE,
                        "apiBaseUrl": INSTANCE + "/api.php/v2",
                    }
                if name == "get_executions_executionID":
                    return {"execution": {"id": 20, "project": 10}}
                if name == "get_stories_storyID":
                    return {"story": {"id": 30, "product": 40}}
                if name == "get_executions_executionID_stories":
                    return {"stories": [{"id": 30}]}
                if name == "get_bug_attachment":
                    return copy.deepcopy(remote.proofs[arguments["fileId"]])
                if name == "get_files_fileID":
                    return {"file": copy.deepcopy(remote.file_metadata.get(arguments["fileID"]))}
                if name == "get_bugs_bugID":
                    if remote.on_bug:
                        callback, remote.on_bug = remote.on_bug, None
                        await callback()
                    return {"bug": copy.deepcopy(remote.bug)}
                raise AssertionError("Restore must not invoke a remote write")

        return Client()


@pytest_asyncio.fixture
async def case():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    source = Settings.from_mapping(
        {
            "security": {
                "integration": {"key": "restore-suite-cipher"},
                "worker": {"key": "other-worker"},
                "integration_worker": {"key": "source-worker"},
            },
            "integration_execution": {
                "enabled": True,
                "all_projects": True,
                "runtime_generation": "source-generation",
            },
        }
    )
    settings = replace(
        source,
        integration_worker_key="restored-worker",
        integration_execution=IntegrationExecutionSettings(
            runtime_generation="restored-generation", accept_submissions=False, claim_enabled=False
        ),
    )
    remote, clock = Remote(), {"now": NOW}
    cipher = IntegrationCredentialCipher(source.integration_key)
    async with sessions() as session:
        session.add_all(
            [
                User(user_id="u", nickname="owner"),
                User(user_id="v", nickname="other"),
                Project(project_id="p", user_id="u", name="restore"),
            ]
        )
        await session.flush()
        session.add(
            Sprint(
                sprint_id="s",
                project_id="p",
                name="sprint",
                start_time=NOW,
                end_time=NOW + timedelta(days=1),
            )
        )
        await session.flush()
        session.add(Requirement(requirement_id="r", sprint_id="s", name="requirement"))
        session.add(
            Bug(
                bug_id="b",
                project_id="p",
                bug_no=1,
                title="Restored",
                description_html="<p>restored</p>",
                found_sprint_id="s",
                requirement_id="r",
                reporter_user_id="u",
            )
        )
        session.add(
            SharedService(
                service_id="svc",
                project_id="p",
                provider="mcp",
                template_id="zentao",
                name="fixture",
                base_url="http://mcp.fixture/zentao/mcp",
                zentao_instance_url=INSTANCE,
            )
        )
        session.add(
            IntegrationConnection(
                connection_id="connection",
                project_id="p",
                user_id="u",
                provider="mcp",
                name="personal",
                secret_json={"token": cipher.encrypt("owner-personal-token")},
            )
        )
        await session.flush()
        session.add(ServiceAuthorization(service_id="svc", user_id="u", connection_id="connection"))
        for kind, local, external, identifier, parent in (
            ("project", "p", "project", "10", ""),
            ("sprint", "s", "execution", "20", "10"),
            ("requirement", "r", "story", "30", "20"),
        ):
            session.add(
                ResourceBinding(
                    binding_id=kind,
                    user_id="u",
                    provider="zentao",
                    instance_url=INSTANCE,
                    instance_key=instance_key(INSTANCE),
                    connection_id="connection",
                    local_resource_type=kind,
                    local_resource_id=local,
                    remote_resource_type=external,
                    remote_resource_id=identifier,
                    remote_parent_id=parent,
                    extra_json={"mcpServiceId": "svc"},
                )
            )
        await session.commit()

    def coordinator(session, config=settings):
        value = build_integration_bug_service(session, config)
        value.pushes.client_factory = remote.factory
        return value

    def service(session):
        value = coordinator(session)
        return IntegrationRestoreService(
            session, value.pushes, value.authorization, settings, clock=lambda: clock["now"]
        )

    yield {
        "sessions": sessions,
        "source": source,
        "settings": settings,
        "remote": remote,
        "clock": clock,
        "coordinator": coordinator,
        "service": service,
        "cipher": cipher,
    }
    await engine.dispose()


async def restore(case, *, queued=True, mapped=False):
    async with case["sessions"]() as session:
        if mapped:
            target = (
                await case["coordinator"](session).pushes.local_context(
                    await session.get(Bug, 1), "u"
                )
            )[2]
            session.add(
                BugZentaoPush(
                    bug_id="b",
                    operation_id="original-create",
                    actor_user_id="u",
                    service_id="svc",
                    instance_url=INSTANCE,
                    status="succeeded",
                    remote_bug_id=50,
                    target_json=target,
                    payload_json={
                        "title": "Restored",
                        "productID": 40,
                        "openedBuild": ["trunk"],
                        "assignedTo": "",
                    },
                    description_status="succeeded",
                    description_operation_id="original-description",
                    description_sync_json={
                        "sourceHtml": "<p>restored</p>",
                        "sourceHash": source_hash("<p>restored</p>"),
                        "desiredSteps": "<p>restored</p>",
                    },
                )
            )
            await session.commit()
        job_id = None
        if queued:
            summary = await case["coordinator"](session, case["source"]).submit(
                "u", "b", IntegrationSyncRequest(request_id="original-request"), "zentao_bug_sync"
            )
            job_id = summary["jobId"]
            job = await session.scalar(
                select(IntegrationJob).where(IntegrationJob.job_id == job_id)
            )
            job.recovery_required, job.status, job.active_scope = True, "quarantined", None
        from testing_agent.services.integration_runtime import key_digest

        session.add(
            IntegrationRuntime(
                id=1,
                restore_id="restore",
                runtime_generation="restored-generation",
                worker_key_digest=key_digest("restored-worker"),
                blocked=True,
            )
        )
        await session.commit()
        return job_id


def request(**kwargs):
    return IntegrationRestoreAudit(
        restore_id="restore", actor_user_id="u", bug_id="b", remote_bug_id=50, **kwargs
    )


@pytest.mark.parametrize("legacy_noop_ids", [False, True])
async def test_positive_proof_links_external_bug_cancels_old_task_and_allows_only_new_requests(
    case,
    legacy_noop_ids,
):
    job_id = await restore(case)
    async with case["sessions"]() as session:
        result = await case["service"](session).audit(request())
        assert result["reviewedJobs"] == 1
        row = await session.scalar(select(BugZentaoPush))
        assert row.remote_bug_id == 50 and row.status == "succeeded"
        job = await session.scalar(select(IntegrationJob))
        assert not job.recovery_required and job.status == "canceled"
        steps = (await session.scalars(select(IntegrationJobStep))).all()
        assert all(step.status == "noop" for step in steps)
        assert all(
            step.receipts_json[-1]["source"] == "restore_readonly_verification" for step in steps
        )
        if legacy_noop_ids:
            # Previously reviewed databases may already link readonly receipts to domain IDs.
            steps[0].operation_id = row.operation_id
            steps[1].operation_id = row.description_operation_id
            await session.commit()
            await case["service"](session).audit(request())
        assert (await case["service"](session).release("restore"))["blocked"] is False
        assert (await session.get(IntegrationRuntime, 1)).blocked is False
        assert all(name.startswith("get_") for name, _ in case["remote"].calls)
        assert set(case["remote"].tokens) == {"owner-personal-token"}
        enabled = replace(
            case["settings"],
            integration_execution=replace(
                case["settings"].integration_execution,
                enabled=True,
                all_projects=True,
                accept_submissions=True,
                claim_enabled=True,
            ),
        )
        response = await case["coordinator"](session, enabled).submit(
            "u", "b", IntegrationSyncRequest(request_id="new-manual-request"), "zentao_bug_sync"
        )
        assert response["jobId"] != job_id and response["jobStatus"] == "queued"
        coordinator = case["coordinator"](session, enabled)
        claimed = (
            await coordinator.claim(
                IntegrationClaimRequest(
                    worker_id="new-worker",
                    claim_request_id="new-claim",
                    protocol_versions=[1],
                    task_types=["zentao_bug_sync"],
                )
            )
        )["job"]
        identity = IntegrationWorkerIdentity.model_validate(
            {key: claimed[key] for key in ("workerId", "claimGeneration", "runtimeGeneration")}
        )
        view = await coordinator.input(response["jobId"], identity)
        access = await coordinator.access(response["jobId"], identity)
        for key, data in (
            ("create_bug", {"result": {"remoteBugId": 50}}),
            (
                "update_description",
                {
                    "remoteBugId": 50,
                    "beforeSteps": "<p>restored</p>",
                    "desiredSteps": "<p>restored</p>",
                    "imagePaths": {},
                    "imageExtensions": {},
                    "result": {"descriptionHash": source_hash("<p>restored</p>")},
                },
            ),
        ):
            receipt = await coordinator.prepare(
                response["jobId"],
                key,
                IntegrationPrepareRequest(
                    **identity.model_dump(),
                    prepare_request_id="new-" + key,
                    input_revision=view["inputRevision"],
                    target_revision=view["targetRevision"],
                    access_revision=access["accessRevision"],
                    decision="noop",
                    input=data,
                ),
            )
            assert not receipt["writeAllowed"]
        current = await coordinator.get("u", "b", response["jobId"])
        assert current["jobStatus"] == "succeeded"
        assert (
            await session.scalar(select(IntegrationJob).where(IntegrationJob.job_id == job_id))
        ).status == "canceled"
        # Read-only recovery remains available after release; old writes have
        # no service fallback and are rejected by the retired HTTP entry.
        await case["coordinator"](session, enabled).guard_recovery("u", "b")
        await session.rollback()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 51),
        ("product", 41),
        ("execution", 21),
        ("title", "Other"),
        ("steps", "foreign edit"),
        ("deleted", "yes"),
    ],
)
async def test_contradictory_remote_object_keeps_quarantine_and_does_not_create_mapping(
    case, field, value
):
    await restore(case)
    case["remote"].bug[field] = value
    async with case["sessions"]() as session:
        with pytest.raises(AppError):
            await case["service"](session).audit(request())
        await session.rollback()
        assert await session.scalar(select(BugZentaoPush)) is None
        assert (await session.scalar(select(IntegrationJob))).recovery_required
        assert (await session.get(IntegrationRuntime, 1)).blocked


async def test_owner_change_during_remote_read_cannot_commit_old_authority(case):
    await restore(case)

    async def transfer():
        async with case["sessions"]() as session:
            project = await session.scalar(select(Project))
            project.user_id = "v"
            await session.commit()

    case["remote"].on_bug = transfer
    async with case["sessions"]() as session:
        with pytest.raises(AppError) as denied:
            await case["service"](session).audit(request())
        assert denied.value.http_code == 403
        await session.rollback()
        assert await session.scalar(select(IntegrationRestoreReview)) is None
        assert await session.scalar(select(BugZentaoPush)) is None


async def test_credential_replacement_during_read_invalidates_proof(case):
    await restore(case)

    async def rotate():
        async with case["sessions"]() as session:
            connection = await session.scalar(select(IntegrationConnection))
            connection.secret_json = {"token": case["cipher"].encrypt("replacement-personal-token")}
            await session.commit()

    case["remote"].on_bug = rotate
    async with case["sessions"]() as session:
        with pytest.raises(AppError, match="授权已变化"):
            await case["service"](session).audit(request())
        await session.rollback()
        assert await session.scalar(select(BugZentaoPush)) is None


async def test_release_requires_every_current_mapping_and_quarantined_scope_reviewed(case):
    await restore(case, queued=True)
    async with case["sessions"]() as session:
        with pytest.raises(AppError, match="未核对"):
            await case["service"](session).release("restore")
        await session.rollback()
        assert (await session.get(IntegrationRuntime, 1)).blocked
        await case["service"](session).isolate("restore", bug_id="b")
        result = await case["service"](session).release("restore")
        assert result["isolatedScopes"] == 1 and not result["blocked"]
        assert (await session.scalar(select(IntegrationJob))).recovery_required
        enabled = replace(
            case["settings"],
            integration_execution=replace(
                case["settings"].integration_execution,
                enabled=True,
                all_projects=True,
                accept_submissions=True,
            ),
        )
        with pytest.raises(AppError, match="继续保持隔离"):
            await case["coordinator"](session, enabled).submit(
                "u", "b", IntegrationSyncRequest(request_id="must-not-replay"), "zentao_bug_sync"
            )
        await session.rollback()


async def test_current_mapping_and_proof_age_are_checked_again_before_release(case):
    await restore(case, queued=False, mapped=True)
    async with case["sessions"]() as session:
        await case["service"](session).audit(request())
        case["clock"]["now"] += timedelta(seconds=3601)
        with pytest.raises(AppError, match="已过期"):
            await case["service"](session).release("restore")
        await session.rollback()
        case["clock"]["now"] = NOW
        row = await session.scalar(select(BugZentaoPush))
        row.remote_bug_id = 51
        await session.commit()
        with pytest.raises(AppError):
            await case["service"](session).release("restore")
        await session.rollback()
        assert (await session.get(IntegrationRuntime, 1)).blocked


async def test_attachment_restore_requires_explicit_id_and_exact_remote_bytes(case):
    async with case["sessions"]() as session:
        session.add(
            StoredFile(
                file_id="f",
                project_id="p",
                uploaded_by="u",
                filename="log.txt",
                content_type="text/plain",
                size=3,
                sha256=digest("file"),
                bucket="private",
                object_key="key",
                staging_key="staging",
                status="attached",
                purpose="attachment",
                resource_type="bug",
                resource_id="b",
                expires_at=NOW + timedelta(days=1),
            )
        )
        await session.commit()
    await restore(case)
    case["remote"].bug["files"] = [{"id": 101, "objectType": "bug", "objectID": 50}]
    case["remote"].proofs[101] = {
        "id": 101,
        "sha256": digest("other"),
        "size": 3,
        "status": "success",
    }
    async with case["sessions"]() as session:
        with pytest.raises(AppError, match="提供"):
            await case["service"](session).audit(request())
        await session.rollback()
        with pytest.raises(AppError, match="字节"):
            await case["service"](session).audit(request(files={"f": 101}))
        await session.rollback()
        case["remote"].proofs[101]["sha256"] = digest("file")
        await case["service"](session).audit(request(files={"f": 101}))
        assert (await session.scalar(select(BugZentaoAttachment))).remote_file_id == 101


async def test_failed_local_commit_rolls_back_mapping_and_review_together(case, monkeypatch):
    await restore(case)
    async with case["sessions"]() as session:
        service = case["service"](session)
        original = service.save_review

        async def interrupted(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("after review flush")

        monkeypatch.setattr(service, "save_review", interrupted)
        with pytest.raises(RuntimeError, match="flush"):
            await service.audit(request())
        await session.rollback()
        assert await session.scalar(select(BugZentaoPush)) is None
        assert await session.scalar(select(IntegrationRestoreReview)) is None
        assert (await session.scalar(select(IntegrationJob))).recovery_required


async def test_isolated_scope_can_later_be_verified_without_replaying_old_task(case):
    job_id = await restore(case)
    async with case["sessions"]() as session:
        await case["service"](session).isolate("restore", job_id=job_id)
        await case["service"](session).release("restore")
        assert (await session.get(IntegrationRuntime, 1)).blocked is False
        await case["service"](session).audit(request())
        assert not (await session.scalar(select(IntegrationJob))).recovery_required
        decisions = (await session.scalars(select(IntegrationRestoreReview))).all()
        assert all(row.decision == "verified" for row in decisions)
        old = IntegrationResultRequest(
            worker_id="old-worker",
            claim_generation=1,
            runtime_generation="source-generation",
            operation_id="created-after-backup",
            event_id="late-event",
            status="succeeded",
            result={"remoteBugId": 50},
        )
        with pytest.raises(AppError):
            await case["coordinator"](session).result(job_id, "create_bug", old, evidence=True)
        await session.rollback()
        assert (await session.scalar(select(BugZentaoPush))).remote_bug_id == 50


async def test_retained_isolation_cannot_delete_or_retarget_associations_after_global_release(case):
    await restore(case)
    from testing_agent.services.integration_guards import require_no_active_job
    from testing_agent.services.integration_lifecycle import guard_integrations

    async with case["sessions"]() as session:
        await case["service"](session).isolate("restore", bug_id="b")
        await case["service"](session).release("restore")
        with pytest.raises(AppError):
            await require_no_active_job(session, "b")
        await session.rollback()
        with pytest.raises(AppError):
            await guard_integrations(session, project_id="p", include_unknown=False)
        await session.rollback()


async def test_legacy_unknown_field_is_only_confirmed_when_actual_values_match(case):
    await restore(case, queued=False, mapped=True)
    async with case["sessions"]() as session:
        row = await session.scalar(select(BugZentaoPush))
        row.payload_json = {
            **row.payload_json,
            "_fieldUpdate": {
                "operationId": "field-op",
                "status": "unknown",
                "desired": {"openedBuild": ["trunk"], "assignedTo": "dev"},
            },
        }
        await session.commit()
        with pytest.raises(AppError, match="仍未确认"):
            await case["service"](session).audit(request())
        await session.rollback()
        assert (await session.get(IntegrationRuntime, 1)).blocked
        case["remote"].bug["assignedTo"] = "dev"
        await case["service"](session).audit(request())
        row = await session.scalar(select(BugZentaoPush))
        assert (
            row.payload_json["assignedTo"] == "dev"
            and row.payload_json["_fieldUpdate"]["status"] == "succeeded"
        )


async def test_unknown_description_different_from_original_intent_remains_isolated(case):
    await restore(case, queued=False, mapped=True)
    async with case["sessions"]() as session:
        row = await session.scalar(select(BugZentaoPush))
        row.description_status = "unknown"
        row.description_sync_json = {
            **row.description_sync_json,
            "desiredSteps": "<p>new intent</p>",
        }
        await session.commit()
        with pytest.raises(AppError, match="尚未确认"):
            await case["service"](session).audit(request())
        await session.rollback()
        assert (await session.scalar(select(BugZentaoPush))).description_status == "unknown"


async def test_non_owner_cannot_borrow_original_actors_personal_authorization(case):
    await restore(case)
    async with case["sessions"]() as session:
        with pytest.raises(AppError) as denied:
            await case["service"](session).audit(
                request().model_copy(update={"actor_user_id": "v"})
            )
        assert denied.value.http_code == 403
        assert not case["remote"].tokens


async def test_confirmed_remote_description_keeps_old_baseline_when_local_content_is_new(case):
    await restore(case, queued=False, mapped=True)
    async with case["sessions"]() as session:
        bug = await session.scalar(select(Bug))
        bug.description_html = "<p>new local draft</p>"
        await session.commit()
        await case["service"](session).audit(request())
        row = await session.scalar(select(BugZentaoPush))
        assert row.description_sync_json["desiredSteps"] == "<p>restored</p>"
        assert row.description_sync_json["sourceHash"] != source_hash(bug.description_html)


@pytest.mark.parametrize("status", ["succeeded", "unknown"])
async def test_equivalent_restore_html_preserves_original_operation_proof_bytes(case, status):
    await restore(case, queued=False, mapped=True)
    original = "<p>restored</p>\n"
    async with case["sessions"]() as session:
        row = await session.scalar(select(BugZentaoPush))
        row.description_status = status
        row.description_sync_json = {**row.description_sync_json, "desiredSteps": original}
        await session.commit()
        await case["service"](session).audit(request())
        row = await session.scalar(select(BugZentaoPush))
        assert row.description_operation_id == "original-description"
        assert row.description_status == "succeeded"
        assert row.description_sync_json["desiredSteps"] == original
        assert source_hash(row.description_sync_json["desiredSteps"]) == source_hash(original)


@pytest.mark.parametrize("foreign", [False, True])
async def test_inline_image_hidden_from_bug_files_uses_native_file_lookup(case, foreign):
    async with case["sessions"]() as session:
        bug = await session.scalar(select(Bug))
        bug.description_html = '<p>restored<img data-file-id="f"></p>'
        session.add(
            StoredFile(
                file_id="f",
                project_id="p",
                uploaded_by="u",
                filename="image.png",
                content_type="image/png",
                size=3,
                sha256=digest("file"),
                bucket="private",
                object_key="key",
                staging_key="staging",
                status="attached",
                purpose="attachment",
                resource_type="bug",
                resource_id="b",
                expires_at=NOW + timedelta(days=1),
            )
        )
        await session.commit()
    await restore(case)
    case["remote"].bug["steps"] = '<p>restored<img src="' + INSTANCE + '/file-read-101.png" ></p>'
    case["remote"].file_metadata[101] = {
        "id": 101,
        "objectType": "bug",
        "objectID": 51 if foreign else 50,
        "extension": "png",
    }
    case["remote"].proofs[101] = {
        "id": 101,
        "sha256": digest("file"),
        "size": 3,
        "status": "success",
    }
    async with case["sessions"]() as session:
        if foreign:
            with pytest.raises(AppError, match="归属"):
                await case["service"](session).audit(request(files={"f": 101}))
            await session.rollback()
            assert await session.scalar(select(BugZentaoPush)) is None
        else:
            await case["service"](session).audit(request(files={"f": 101}))
            assert (await session.scalar(select(BugZentaoAttachment))).remote_file_id == 101
