"""Candidate generation is authorized and idempotent on real MySQL."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.generation import generation_services
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401
from support.requirement_versions import material_artifact, points_artifact, scope_artifact

from testing_agent.core.errors import AppError
from testing_agent.models import Base
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateRevisionRequest,
    CandidateRunRequest,
)
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication
from testing_agent.services.generation_candidate_relations import CandidateRelations
from testing_agent.services.generation_chain_initialization import CandidateChainInitialization
from testing_agent.services.generation_dispatch_application import CandidateDispatchApplication
from testing_agent.services.generation_revision_application import CandidateRevisionApplication
from testing_agent.services.repo_gitlab_access import RepoGitlabAccess
from testing_agent.services.repository_profile_adoption import RepositoryProfileAdoption
from testing_agent.services.requirement_material_source import (
    material_reference_fields,
    material_source,
)
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.ui_generation_source import ResolvedUiSource

DATA = b"requirement document"
IMAGE = b"verified image bytes"


class Storage:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def get_object(self, key):
        self.calls += 1
        assert not self.fail and key == "document"
        return {"Body": self}

    def iter_chunks(self, chunk_size):
        yield DATA

    def close(self):
        pass


def test_generation_application_replays_concurrent_dispatch(mysql):  # noqa: F811
    tables = Base.metadata.tables
    digest = sha256(DATA).hexdigest()
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        actor = project["user_id"]
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            conn,
            tables["requirements"],
            {
                "requirement_id": "req",
                "sprint_id": sprint["sprint_id"],
                "document_type": "docx",
                "document_file_id": "document",
                "document_filename": "requirement.docx",
                "document_hash": digest,
            },
        )
        seed_row(
            conn,
            tables["stored_files"],
            {
                "file_id": "document",
                "project_id": project["project_id"],
                "uploaded_by": actor,
                "filename": "requirement.docx",
                "content_type": "application/octet-stream",
                "size": len(DATA),
                "sha256": digest,
                "bucket": "bucket",
                "object_key": "document",
                "staging_key": "",
                "status": "attached",
                "purpose": "requirement",
                "resource_type": "requirement",
                "resource_id": "req",
                "expires_at": datetime.now(UTC) + timedelta(days=1),
            },
        )
        seed_row(
            conn,
            tables["stored_files"],
            {
                "file_id": "image",
                "project_id": project["project_id"],
                "uploaded_by": actor,
                "filename": "image.png",
                "content_type": "image/png",
                "size": len(IMAGE),
                "sha256": sha256(IMAGE).hexdigest(),
                "bucket": "bucket",
                "object_key": "image",
                "staging_key": "",
                "status": "ready",
                "purpose": "attachment",
                "resource_type": "",
                "resource_id": "",
                "expires_at": datetime.now(UTC) + timedelta(days=1),
            },
        )
        seed_row(
            conn,
            tables["integration_connections"],
            {
                "connection_id": "llm",
                "project_id": project["project_id"],
                "user_id": actor,
                "provider": "llm",
                "name": "model",
                "status": "active",
                "secret_json": {"apiKey": "test-only"},
            },
        )
        task = seed_row(
            conn,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": "req",
                "task_type": "requirement_analysis",
            },
        )
        chain = seed_row(
            conn,
            tables["requirement_generation_chains"],
            {
                "requirement_id": "req",
                "kind": "requirement_analysis",
                "task_id": task["task_id"],
            },
        )
        stage = seed_row(
            conn,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "extracting_text"},
        )
        seed_row(
            conn,
            tables["ai_generation_stage_contents"],
            {
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "stage": "extracting_text",
                "source_candidate_id": None,
                "content_token": "empty",
            },
        )

    async def exercise():
        engine, factory = async_sessions(mysql)
        storage = Storage()
        files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)
        request = CandidateRunRequest(connection_id="llm", request_id=uuid4())

        def app(session):
            return CandidateDispatchApplication(
                generation_services(AiGenerateTaskRepository(session), files=files).chain
            )

        async def submit():
            async with factory() as session:
                return await app(session).run(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id=actor,
                )

        try:
            async with factory() as session:
                with pytest.raises(AppError):
                    await app(session).run(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        request=request.model_copy(update={"connection_id": "missing"}),
                        actor_id=actor,
                    )
                assert storage.calls == 0
            results = await asyncio.gather(submit(), submit())
            assert sorted(item.replayed for item in results) == [False, True]
            assert results[0].attempt_id == results[1].attempt_id
            async with factory() as session:
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationAttempt)
                    )
                    == 1
                )
                assert await session.scalar(sa.select(sa.func.count()).select_from(WorkerTask)) == 1
                storage.fail = True
                calls = storage.calls
                replay = await app(session).run(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id=actor,
                )
                assert (
                    replay.replayed
                    and replay.attempt_id == results[0].attempt_id
                    and storage.calls == calls
                )
            storage.fail = False
            async with factory() as session:
                await StageWorkerTransitions(session).completed(
                    stage["id"],
                    results[0].attempt_id,
                    str(request.request_id),
                    content=json.dumps(material_artifact(), ensure_ascii=False),
                    output_format="json",
                    output_context=None,
                )
                await session.commit()
                candidate = await session.scalar(
                    sa.select(AiGenerationCandidate).where(
                        AiGenerationCandidate.origin_attempt_id == results[0].attempt_id
                    )
                )
                assert candidate is not None
                adoption = CandidateAdoptRequest(
                    action="adopt",
                    candidate_id=candidate.candidate_id,
                    expected_candidate_token=candidate.candidate_token,
                    expected_attempt_id=candidate.current_attempt_id,
                    expected_current_token="empty",
                    request_id=uuid4(),
                )
                await CandidateAdoptionApplication(
                    generation_services(AiGenerateTaskRepository(session), files=files).chain
                ).adopt(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=adoption,
                    actor_id=actor,
                )
                session.add(
                    AiGenerateTask(
                        task_id="risk-task",
                        task_type="code_risk_analysis",
                        name="risk",
                        project_id=project["project_id"],
                        sprint_id=sprint["sprint_id"],
                        requirement_id="req",
                        creator_user_id=actor,
                        source_type="text",
                        source_content="",
                    )
                )
                await session.commit()

            class RevisionStorage(Storage):
                def get_object(self, key):
                    assert key in {"document", "image"}
                    return {
                        "Body": SimpleNamespace(
                            iter_chunks=lambda size: [DATA if key == "document" else IMAGE],
                            close=lambda: None,
                        )
                    }

            revision_request = CandidateRevisionRequest(
                expected_candidate_token=adoption.expected_candidate_token,
                expected_attempt_id=adoption.expected_attempt_id,
                connection_id="llm",
                instruction="参考图片补充边界",
                request_id=uuid4(),
                attachment_file_ids=["image"],
            )

            async def revise():
                async with factory() as session:
                    revision_files = StoredFileService(
                        session, SimpleNamespace(bucket="bucket", enabled=True), RevisionStorage()
                    )
                    chain_service = generation_services(
                        AiGenerateTaskRepository(session), files=revision_files
                    ).chain
                    return await CandidateRevisionApplication(chain_service).run(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        candidate_id=adoption.candidate_id,
                        request=revision_request,
                        actor_id=actor,
                    )

            revisions = await asyncio.gather(revise(), revise())
            assert sorted(item.replayed for item in revisions) == [False, True]
            assert revisions[0].attempt_id == revisions[1].attempt_id
            revised = revisions[0]
            async with factory() as session:
                image = await session.scalar(
                    sa.select(StoredFile).where(StoredFile.file_id == "image")
                )
                assert image is not None and image.status == "attached"
                assert image.resource_id == revised.attempt_id
                await StageWorkerTransitions(session).completed(
                    stage["id"],
                    revised.attempt_id,
                    str(revision_request.request_id),
                    content=json.dumps(material_artifact(), ensure_ascii=False),
                    output_format="json",
                    output_context=None,
                )
                await session.commit()
                derived = await session.scalar(
                    sa.select(AiGenerationCandidate).where(
                        AiGenerationCandidate.origin_attempt_id == revised.attempt_id
                    )
                )
                assert (
                    derived is not None
                    and derived.derived_from_candidate_id == adoption.candidate_id
                )
                slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stage["id"]
                    )
                )
                assert slot is not None and slot.source_candidate_id == adoption.candidate_id
                review = CandidateAdoptRequest(
                    action="adopt",
                    candidate_id=derived.candidate_id,
                    expected_candidate_token=derived.candidate_token,
                    expected_attempt_id=derived.current_attempt_id,
                    expected_current_token=slot.content_token,
                    request_id=uuid4(),
                )
                revision_files = StoredFileService(
                    session, SimpleNamespace(bucket="bucket", enabled=True), RevisionStorage()
                )
                check = await CandidateAdoptionApplication(
                    generation_services(
                        AiGenerateTaskRepository(session), files=revision_files
                    ).chain
                ).preview(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=review,
                    actor_id=actor,
                )
                assert check.can_adopt
                await session.execute(
                    sa.update(StoredFile)
                    .where(StoredFile.file_id == "image")
                    .values(status="deleting")
                )
                await session.commit()
                with pytest.raises(AppError, match="来源信息不完整"):
                    await CandidateAdoptionApplication(
                        generation_services(
                            AiGenerateTaskRepository(session), files=revision_files
                        ).chain
                    ).preview(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        request=review,
                        actor_id=actor,
                    )
                await session.execute(
                    sa.update(StoredFile)
                    .where(StoredFile.file_id == "image")
                    .values(status="attached")
                )
                await session.commit()
                await session.execute(
                    sa.update(StoredFile)
                    .where(StoredFile.file_id == "image")
                    .values(resource_id="another-attempt")
                )
                await session.commit()
                with pytest.raises(AppError, match="来源信息不完整"):
                    await CandidateAdoptionApplication(
                        generation_services(
                            AiGenerateTaskRepository(session), files=revision_files
                        ).chain
                    ).preview(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        request=review,
                        actor_id=actor,
                    )
                await session.execute(
                    sa.update(StoredFile)
                    .where(StoredFile.file_id == "image")
                    .values(resource_id=revised.attempt_id)
                )
                await session.commit()

            arrived, resume = asyncio.Event(), asyncio.Event()

            class AuxiliarySource:
                async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
                    chosen = kwargs["current_material"]
                    arrived.set()
                    await asyncio.wait_for(resume.wait(), timeout=10)
                    return {
                        "requirement": {"documentContent": material_source(chosen)},
                        **material_reference_fields(chosen),
                    }

            async def launch():
                async with factory() as session:
                    launcher = generation_services(
                        AiGenerateTaskRepository(session),
                        files=files,
                        code_risk_analysis_service=AuxiliarySource(),
                    ).launcher
                    return await launcher.launch(
                        "code_risk_analysis", "risk-task", {"connectionId": "llm"}, actor
                    )

            pending = asyncio.create_task(launch())
            await asyncio.wait_for(arrived.wait(), timeout=10)
            async with factory() as writer:
                await asyncio.wait_for(
                    writer.execute(
                        sa.update(AiGenerationStageContent)
                        .where(AiGenerationStageContent.stage_id == stage["id"])
                        .values(content_token="changed-while-preparing")
                    ),
                    timeout=3,
                )
                await writer.commit()
            resume.set()
            with pytest.raises(AppError) as changed:
                await pending
            assert changed.value.data["reason"] == "concurrent_change"
            async with factory() as session:
                assert (
                    await session.scalar(
                        sa.select(sa.func.count())
                        .select_from(AiExecution)
                        .where(AiExecution.task_id == "risk-task")
                    )
                    == 0
                )
            result = await launch()
            async with factory() as session:
                attempt = await session.scalar(
                    sa.select(AiGenerationAttempt).where(
                        AiGenerationAttempt.execution_id == result["runId"]
                    )
                )
                assert attempt is not None
                actual = attempt.input_snapshot_json["source"]
                assert (
                    actual["requirementMaterialCurrent"]["currentToken"]
                    == "changed-while-preparing"
                )
                assert "requirementMaterialVersion" not in actual

            async with factory() as session:
                session.add(
                    AiGenerateTask(
                        task_id="profile-task",
                        task_type="repository_profile",
                        name="profile",
                        project_id=project["project_id"],
                        sprint_id=sprint["sprint_id"],
                        requirement_id="req",
                        creator_user_id=actor,
                        source_type="text",
                        source_content="",
                    )
                )
                await session.commit()

            class ProfileSource:
                async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
                    chosen = kwargs["current_material"]
                    return {
                        "taskId": task.task_id,
                        "taskType": task.task_type,
                        "requirementId": task.requirement_id,
                        "requirement": {"documentContent": material_source(chosen)},
                        "bindings": [],
                        **material_reference_fields(chosen),
                    }

            async def create_profile(summary):
                async with factory() as session:
                    launcher = generation_services(
                        AiGenerateTaskRepository(session),
                        files=files,
                        repository_profile_service=ProfileSource(),
                    ).launcher
                    run = await launcher.launch(
                        "repository_profile", "profile-task", {"connectionId": "llm"}, actor
                    )
                    attempt = await session.scalar(
                        sa.select(AiGenerationAttempt).where(
                            AiGenerationAttempt.execution_id == run["runId"]
                        )
                    )
                    await StageWorkerTransitions(session).completed(
                        attempt.stage_id,
                        attempt.id,
                        attempt.worker_task_id,
                        content=json.dumps({"repositories": [], "overallSummary": summary}),
                        output_format="json",
                        output_context=None,
                    )
                    await session.commit()
                    candidate = await session.scalar(
                        sa.select(AiGenerationCandidate).where(
                            AiGenerationCandidate.origin_attempt_id == attempt.id
                        )
                    )
                    return (
                        candidate.candidate_id,
                        candidate.candidate_token,
                        candidate.current_attempt_id,
                    )

            first_profile = await create_profile("first")
            second_profile = await create_profile("second")
            async with factory() as session:
                profile_slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id
                        == sa.select(AiGenerationAttempt.stage_id)
                        .where(AiGenerationAttempt.id == first_profile[2])
                        .scalar_subquery()
                    )
                )
                empty_token = profile_slot.content_token
                assert profile_slot.source_candidate_id is None

            def adoption_request(profile):
                return CandidateAdoptRequest(
                    action="adopt",
                    candidate_id=profile[0],
                    expected_candidate_token=profile[1],
                    expected_attempt_id=profile[2],
                    expected_current_token=empty_token,
                    request_id=uuid4(),
                )

            first_request, second_request = (
                adoption_request(first_profile),
                adoption_request(second_profile),
            )

            async def adopt_profile(body):
                async with factory() as session:
                    service = RepositoryProfileAdoption(
                        generation_services(AiGenerateTaskRepository(session), files=files).chain
                    )
                    try:
                        return await service.adopt(
                            requirement_id="req", request=body, actor_id=actor
                        )
                    except AppError:
                        await session.rollback()
                        return None

            competing = await asyncio.wait_for(
                asyncio.gather(adopt_profile(first_request), adopt_profile(second_request)),
                timeout=15,
            )
            assert sum(item is not None for item in competing) == 1
            winner = first_request if competing[0] is not None else second_request
            replayed = await adopt_profile(winner)
            assert replayed is not None and replayed.replayed
            await create_profile("third")
            async with factory() as session:
                current = await session.get(AiGenerationStageContent, profile_slot.stage_id)
                assert current.source_candidate_id == winner.candidate_id

            async with factory() as session:
                session.add(
                    AiGenerateTask(
                        task_id="ui-task",
                        task_type="ui_case_generate",
                        name="ui",
                        project_id=project["project_id"],
                        sprint_id=sprint["sprint_id"],
                        requirement_id="req",
                        creator_user_id=actor,
                        source_type="repository",
                        source_content="",
                    )
                )
                session.add(
                    SoftwareRepository(
                        software_repository_id="ui-repo",
                        project_id=project["project_id"],
                        name="ui",
                        description="",
                        base_path="",
                        repository_project_id="git-id",
                        repository_group_id="group",
                        repository_instance_key="instance",
                        repository_path="team/ui",
                        repository_name="ui",
                        repository_instance_url="https://git.example",
                        version=1,
                        created_by_user_id=actor,
                    )
                )
                session.add(
                    FunctionTestSuite(suite_id="ui-cases", requirement_id="req", name="功能")
                )
                await session.flush()
                session.add(
                    FunctionTestCase(case_id="ui-case", suite_id="ui-cases", title="功能用例")
                )
                await session.commit()
                chain_service = generation_services(
                    AiGenerateTaskRepository(session), files=files
                ).chain
                await CandidateChainInitialization(chain_service).initialize(
                    requirement_id="req", kind="ui", task_id="ui-task", actor_id=actor
                )

            git_arrived, git_resume = asyncio.Event(), asyncio.Event()
            frozen_repository = {
                "bindingId": "ui-repo",
                "repositoryId": "git-id",
                "instanceUrl": "https://git.example",
                "pathWithNamespace": "team/ui",
                "branch": "main",
                "commit": "fixed-commit",
            }
            frozen_binding = {
                **frozen_repository,
                "headCommit": "fixed-commit",
                "connectionId": "git-connection",
                "cloneUrl": "https://git.example/team/ui.git",
            }

            async def resolve_current(**kwargs):
                git_arrived.set()
                await asyncio.wait_for(git_resume.wait(), timeout=10)
                return ResolvedUiSource(frozen_repository, frozen_binding)

            ui_request = CandidateRunRequest(
                connection_id="llm",
                request_id=uuid4(),
                source_repository_id="git-id",
                source_profile_candidate_id=winner.candidate_id,
                function_case_ids=["ui-case"],
            )

            async def submit_ui():
                async with factory() as session:
                    chain_service = generation_services(
                        AiGenerateTaskRepository(session), files=files
                    ).chain
                    chain_service.ui_sources.resolve_current = resolve_current
                    chain_service.ui_sources.resolve_binding_access = AsyncMock(
                        return_value=RepoGitlabAccess(
                            "git-connection", "https://git.example", "test"
                        )
                    )
                    return await CandidateDispatchApplication(chain_service).run(
                        requirement_id="req",
                        kind="ui",
                        stage="ui_surface",
                        request=ui_request,
                        actor_id=actor,
                    )

            pending_ui = asyncio.create_task(submit_ui())
            await asyncio.wait_for(git_arrived.wait(), timeout=10)
            async with factory() as writer:
                await asyncio.wait_for(
                    writer.execute(
                        sa.update(AiGenerationStageContent)
                        .where(AiGenerationStageContent.stage_id == profile_slot.stage_id)
                        .values(content_token="profile-changed-during-git")
                    ),
                    timeout=3,
                )
                await writer.commit()
            git_resume.set()
            with pytest.raises(AppError) as ui_changed:
                await pending_ui
            assert ui_changed.value.data["reason"] == "concurrent_change"
            ui_results = await asyncio.wait_for(
                asyncio.gather(submit_ui(), submit_ui()), timeout=15
            )
            assert sorted(result.replayed for result in ui_results) == [False, True]
            assert ui_results[0].attempt_id == ui_results[1].attempt_id

            async with factory() as session:
                session.add(
                    AiGenerateTask(
                        task_id="function-task",
                        task_type="functional_case_generate",
                        name="功能",
                        project_id=project["project_id"],
                        sprint_id=sprint["sprint_id"],
                        requirement_id="req",
                        creator_user_id=actor,
                        source_type="text",
                        source_content="",
                    )
                )
                await session.commit()
                chain_service = generation_services(
                    AiGenerateTaskRepository(session), files=files
                ).chain
                await CandidateChainInitialization(chain_service).initialize(
                    requirement_id="req", kind="function", task_id="function-task", actor_id=actor
                )

            async def create_and_adopt(stage_name, artifact, fmt="json"):
                async with factory() as session:
                    chain_service = generation_services(
                        AiGenerateTaskRepository(session), files=files
                    ).chain
                    run_request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
                    result = await CandidateDispatchApplication(chain_service).run(
                        requirement_id="req",
                        kind="function",
                        stage=stage_name,
                        request=run_request,
                        actor_id=actor,
                    )
                    attempt = await session.scalar(
                        sa.select(AiGenerationAttempt).where(
                            AiGenerationAttempt.id == result.attempt_id
                        )
                    )
                    await StageWorkerTransitions(session).completed(
                        attempt.stage_id,
                        attempt.id,
                        str(run_request.request_id),
                        content=json.dumps(artifact, ensure_ascii=False)
                        if fmt == "json"
                        else artifact,
                        output_format=fmt,
                        output_context=None,
                    )
                    await session.commit()
                    candidate = await session.scalar(
                        sa.select(AiGenerationCandidate).where(
                            AiGenerationCandidate.origin_attempt_id == result.attempt_id
                        )
                    )
                    candidate_id = candidate.candidate_id
                    slot = await session.scalar(
                        sa.select(AiGenerationStageContent).where(
                            AiGenerationStageContent.stage_id == attempt.stage_id
                        )
                    )
                    adopted = await CandidateAdoptionApplication(chain_service).adopt(
                        requirement_id="req",
                        kind="function",
                        stage=stage_name,
                        actor_id=actor,
                        request=CandidateAdoptRequest(
                            action="adopt",
                            candidate_id=candidate.candidate_id,
                            expected_candidate_token=candidate.candidate_token,
                            expected_attempt_id=candidate.current_attempt_id,
                            expected_current_token=slot.content_token,
                            request_id=uuid4(),
                        ),
                    )
                    return candidate_id, adopted.content_token

            await create_and_adopt("requirement_analysis", scope_artifact())
            await create_and_adopt("case_names", points_artifact())
            first_leaf, first_token = await create_and_adopt(
                "detailed_cases", "cases:\n  - case_id: graph-case\n    title: example\n", "yaml"
            )
            relation_request_id = uuid4()

            async def submit_relation():
                async with factory() as session:
                    chain_service = generation_services(
                        AiGenerateTaskRepository(session), files=files
                    ).chain
                    return await CandidateRelations(chain_service, action="execute").run(
                        requirement_id="req",
                        current_token=first_token,
                        connection_id="llm",
                        request_id=relation_request_id,
                        actor_id=actor,
                    )

            graph_runs = await asyncio.wait_for(
                asyncio.gather(submit_relation(), submit_relation()), timeout=15
            )
            assert sorted(result["replayed"] for result in graph_runs) == [False, True]
            assert graph_runs[0]["attemptId"] == graph_runs[1]["attemptId"]
            async with factory() as session:
                graph_attempt = await session.scalar(
                    sa.select(AiGenerationAttempt).where(
                        AiGenerationAttempt.id == graph_runs[0]["attemptId"]
                    )
                )
                await StageWorkerTransitions(session).completed(
                    graph_attempt.stage_id,
                    graph_attempt.id,
                    str(relation_request_id),
                    content=json.dumps({"schema_version": "2.0", "main_paths": [], "edges": []}),
                    output_format="json",
                    output_context=None,
                )
                await session.commit()
            second_leaf, second_token = await create_and_adopt(
                "detailed_cases", "cases:\n  - case_id: graph-case\n    title: example\n", "yaml"
            )
            assert first_leaf != second_leaf
            async with factory() as session:
                chain_service = generation_services(
                    AiGenerateTaskRepository(session), files=files
                ).chain
                other_graph = await CandidateRelations(chain_service, action="read").view(
                    requirement_id="req",
                    current_token=second_token,
                    actor_id=actor,
                )
                assert (
                    other_graph["status"] == "not_started" and other_graph["caseRelations"] is None
                )
            assert (await submit_relation())["replayed"]
        finally:
            await engine.dispose()

    asyncio.run(exercise())
