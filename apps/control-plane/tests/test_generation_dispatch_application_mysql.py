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
from support.memory_storage import Storage
from support.mysql_initialization import clean_schema as clean_schema
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row
from support.mysql_initialization import sessions as sessions
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
STAGE = dict(requirement_id="req", kind="requirement_analysis", stage="extracting_text")
CASES_YAML = "cases:\n  - case_id: graph-case\n    title: example\n"
GRAPH = {"schema_version": "2.0", "main_paths": [], "edges": []}
FROZEN_REPOSITORY = {
    "bindingId": "ui-repo",
    "repositoryId": "git-id",
    "instanceUrl": "https://git.example",
    "pathWithNamespace": "team/ui",
    "branch": "main",
    "commit": "fixed-commit",
}
FROZEN_BINDING = {
    **FROZEN_REPOSITORY,
    "headCommit": "fixed-commit",
    "connectionId": "git-connection",
    "cloneUrl": "https://git.example/team/ui.git",
}


@pytest.fixture
def seeded(mysql):
    """Requirement ``req`` with a stored document and image, a model connection, an empty slot."""
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
    return SimpleNamespace(
        actor=actor,
        project_id=project["project_id"],
        sprint_id=sprint["sprint_id"],
        stage_id=stage["id"],
    )


@pytest.fixture
def files():
    """File service over the stored document; ``files.storage`` counts and can refuse reads."""
    return SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=Storage(DATA))


def chain_of(session, files):
    return generation_services(AiGenerateTaskRepository(session), files=files).chain


def dispatch_of(session, files):
    return CandidateDispatchApplication(chain_of(session, files))


def auxiliary_launcher(session, files, **services):
    """Launcher whose auxiliary snapshot builders are the given ``services``."""
    return generation_services(AiGenerateTaskRepository(session), files=files, **services).launcher


async def dispatch(sessions, files, actor, request):
    """Run extracting_text for ``actor``; returns the run."""
    async with sessions() as session:
        return await dispatch_of(session, files).run(**STAGE, request=request, actor_id=actor)


async def complete(sessions, stage_id, request_id, attempt_id, output, fmt="json"):
    """Complete the attempt with ``output``."""
    async with sessions() as session:
        await StageWorkerTransitions(session).completed(
            stage_id,
            attempt_id,
            str(request_id),
            content=json.dumps(output, ensure_ascii=False) if fmt == "json" else output,
            output_format=fmt,
            output_context=None,
        )
        await session.commit()


async def add_task(sessions, seeded, task_id, task_type, *, source_type="text"):
    async with sessions() as session:
        session.add(
            AiGenerateTask(
                task_id=task_id,
                task_type=task_type,
                name=task_id,
                project_id=seeded.project_id,
                sprint_id=seeded.sprint_id,
                requirement_id="req",
                creator_user_id=seeded.actor,
                source_type=source_type,
                source_content="",
            )
        )
        await session.commit()


async def current_slot(sessions, stage_id):
    async with sessions() as session:
        return await session.scalar(
            sa.select(AiGenerationStageContent).where(AiGenerationStageContent.stage_id == stage_id)
        )


async def candidate_from(sessions, attempt_id):
    async with sessions() as session:
        return await session.scalar(
            sa.select(AiGenerationCandidate).where(
                AiGenerationCandidate.origin_attempt_id == attempt_id
            )
        )


async def attempt_of(sessions, attempt_id):
    async with sessions() as session:
        return await session.get(AiGenerationAttempt, attempt_id)


async def attempt_of_execution(sessions, run_id):
    async with sessions() as session:
        return await session.scalar(
            sa.select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == run_id)
        )


async def replace_slot_token(sessions, stage_id, token):
    """A competing writer replaces the slot token; later launches must notice the change."""
    async with sessions() as writer:
        await asyncio.wait_for(
            writer.execute(
                sa.update(AiGenerationStageContent)
                .where(AiGenerationStageContent.stage_id == stage_id)
                .values(content_token=token)
            ),
            timeout=3,
        )
        await writer.commit()


async def dispatched_twice(sessions, files, seeded):
    """Submit one dispatch request from two tasks; returns the request and both runs."""
    request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
    runs = await asyncio.gather(
        dispatch(sessions, files, seeded.actor, request),
        dispatch(sessions, files, seeded.actor, request),
    )
    return request, runs


async def adopted_material(sessions, files, seeded):
    """Dispatch, complete and adopt the material; returns its attempt, candidate and adoption."""
    request, runs = await dispatched_twice(sessions, files, seeded)
    attempt_id = runs[0].attempt_id
    await complete(sessions, seeded.stage_id, request.request_id, attempt_id, material_artifact())
    async with sessions() as session:
        candidate = await session.scalar(
            sa.select(AiGenerationCandidate).where(
                AiGenerationCandidate.origin_attempt_id == attempt_id
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
        await CandidateAdoptionApplication(chain_of(session, files)).adopt(
            **STAGE, request=adoption, actor_id=seeded.actor
        )
        await session.commit()
    return SimpleNamespace(attempt_id=attempt_id, candidate=candidate, adoption=adoption)


class RevisionStorage(Storage):
    """Serves the stored document and the image a revision refers to."""

    def get_object(self, key):
        assert key in {"document", "image"}
        return {
            "Body": SimpleNamespace(
                iter_chunks=lambda size: [DATA if key == "document" else IMAGE],
                close=lambda: None,
            )
        }


def revision_files(session):
    return StoredFileService(
        session, SimpleNamespace(bucket="bucket", enabled=True), RevisionStorage()
    )


async def revise(sessions, seeded, adopted, request):
    """Revise the adopted material with the image attached; returns the run."""
    async with sessions() as session:
        chain_service = generation_services(
            AiGenerateTaskRepository(session), files=revision_files(session)
        ).chain
        return await CandidateRevisionApplication(chain_service).run(
            **STAGE,
            candidate_id=adopted.adoption.candidate_id,
            request=request,
            actor_id=seeded.actor,
        )


async def revised_material(sessions, files, seeded):
    """Adopt the material, then revise it from two tasks; returns the adoption, request and runs."""
    adopted = await adopted_material(sessions, files, seeded)
    request = CandidateRevisionRequest(
        expected_candidate_token=adopted.adoption.expected_candidate_token,
        expected_attempt_id=adopted.adoption.expected_attempt_id,
        connection_id="llm",
        instruction="参考图片补充边界",
        request_id=uuid4(),
        attachment_file_ids=["image"],
    )
    revisions = await asyncio.gather(
        revise(sessions, seeded, adopted, request), revise(sessions, seeded, adopted, request)
    )
    return SimpleNamespace(adopted=adopted, request=request, revisions=revisions)


async def derived_material(sessions, files, seeded):
    """Complete a revision; returns the derived candidate and the slot it would replace."""
    revised = await revised_material(sessions, files, seeded)
    attempt_id = revised.revisions[0].attempt_id
    await complete(
        sessions, seeded.stage_id, revised.request.request_id, attempt_id, material_artifact()
    )
    return SimpleNamespace(
        revised=revised,
        attempt_id=attempt_id,
        derived=await candidate_from(sessions, attempt_id),
        slot=await current_slot(sessions, seeded.stage_id),
    )


class MaterialSource:
    """Snapshot builder of an auxiliary run: the adopted material."""

    async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
        chosen = kwargs["current_material"]
        return {
            "requirement": {"documentContent": material_source(chosen)},
            **material_reference_fields(chosen),
        }


class ProfileSource:
    """Snapshot builder of a repository-profile run: the adopted material."""

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


async def launch_risk(sessions, files, seeded, source):
    """Start a code-risk run whose snapshot ``source`` decides when it is ready."""
    async with sessions() as session:
        launcher = auxiliary_launcher(session, files, code_risk_analysis_service=source)
        return await launcher.launch(
            "code_risk_analysis", "risk-task", {"connectionId": "llm"}, seeded.actor
        )


async def create_profile(sessions, files, seeded, summary):
    """Run the profile task and complete it; returns its candidate as an adoption target."""
    async with sessions() as session:
        launcher = auxiliary_launcher(session, files, repository_profile_service=ProfileSource())
        run = await launcher.launch(
            "repository_profile", "profile-task", {"connectionId": "llm"}, seeded.actor
        )
        attempt = await session.scalar(
            sa.select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == run["runId"])
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
        return SimpleNamespace(
            candidate_id=candidate.candidate_id,
            candidate_token=candidate.candidate_token,
            attempt_id=candidate.current_attempt_id,
            stage_id=attempt.stage_id,
        )


def profile_adoption(profile, expected_current_token):
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=profile.candidate_id,
        expected_candidate_token=profile.candidate_token,
        expected_attempt_id=profile.attempt_id,
        expected_current_token=expected_current_token,
        request_id=uuid4(),
    )


async def adopt_profile(sessions, files, seeded, body):
    """Adopt a profile candidate; returns the result, or None when the service refuses."""
    async with sessions() as session:
        service = RepositoryProfileAdoption(chain_of(session, files))
        try:
            return await service.adopt(requirement_id="req", request=body, actor_id=seeded.actor)
        except AppError:
            await session.rollback()
            return None


async def adopted_profile(sessions, files, seeded):
    """Run and adopt one profile candidate; returns it as an adoption target."""
    await add_task(sessions, seeded, "profile-task", "repository_profile")
    profile = await create_profile(sessions, files, seeded, "first")
    empty_token = (await current_slot(sessions, profile.stage_id)).content_token
    assert await adopt_profile(sessions, files, seeded, profile_adoption(profile, empty_token))
    return profile


async def initialize_ui_chain(sessions, files, seeded):
    """Add a UI task over a Git repository with one function case and start its chain."""
    async with sessions() as session:
        session.add(
            AiGenerateTask(
                task_id="ui-task",
                task_type="ui_case_generate",
                name="ui",
                project_id=seeded.project_id,
                sprint_id=seeded.sprint_id,
                requirement_id="req",
                creator_user_id=seeded.actor,
                source_type="repository",
                source_content="",
            )
        )
        session.add(
            SoftwareRepository(
                software_repository_id="ui-repo",
                project_id=seeded.project_id,
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
                created_by_user_id=seeded.actor,
            )
        )
        session.add(FunctionTestSuite(suite_id="ui-cases", requirement_id="req", name="功能"))
        await session.flush()
        session.add(FunctionTestCase(case_id="ui-case", suite_id="ui-cases", title="功能用例"))
        await session.commit()
        await CandidateChainInitialization(chain_of(session, files)).initialize(
            requirement_id="req", kind="ui", task_id="ui-task", actor_id=seeded.actor
        )


def ui_request(profile_candidate_id):
    return CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        source_repository_id="git-id",
        source_profile_candidate_id=profile_candidate_id,
        function_case_ids=["ui-case"],
    )


async def submit_ui(sessions, files, seeded, request, resolve_current):
    """Dispatch the UI surface stage while ``resolve_current`` resolves the repository."""
    async with sessions() as session:
        chain_service = chain_of(session, files)
        chain_service.ui_sources.resolve_current = resolve_current
        chain_service.ui_sources.resolve_binding_access = AsyncMock(
            return_value=RepoGitlabAccess("git-connection", "https://git.example", "test")
        )
        return await CandidateDispatchApplication(chain_service).run(
            requirement_id="req",
            kind="ui",
            stage="ui_surface",
            request=request,
            actor_id=seeded.actor,
        )


async def initialize_function_chain(sessions, files, seeded):
    async with sessions() as session:
        session.add(
            AiGenerateTask(
                task_id="function-task",
                task_type="functional_case_generate",
                name="功能",
                project_id=seeded.project_id,
                sprint_id=seeded.sprint_id,
                requirement_id="req",
                creator_user_id=seeded.actor,
                source_type="text",
                source_content="",
            )
        )
        await session.commit()
        await CandidateChainInitialization(chain_of(session, files)).initialize(
            requirement_id="req", kind="function", task_id="function-task", actor_id=seeded.actor
        )


async def create_and_adopt(sessions, files, seeded, stage_name, artifact, fmt="json"):
    """Run a function stage, complete and adopt its candidate; returns its id and slot token."""
    async with sessions() as session:
        chain_service = chain_of(session, files)
        request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
        result = await CandidateDispatchApplication(chain_service).run(
            requirement_id="req",
            kind="function",
            stage=stage_name,
            request=request,
            actor_id=seeded.actor,
        )
        attempt = await session.scalar(
            sa.select(AiGenerationAttempt).where(AiGenerationAttempt.id == result.attempt_id)
        )
        await StageWorkerTransitions(session).completed(
            attempt.stage_id,
            attempt.id,
            str(request.request_id),
            content=json.dumps(artifact, ensure_ascii=False) if fmt == "json" else artifact,
            output_format=fmt,
            output_context=None,
        )
        await session.commit()
        candidate = await session.scalar(
            sa.select(AiGenerationCandidate).where(
                AiGenerationCandidate.origin_attempt_id == result.attempt_id
            )
        )
        slot = await session.scalar(
            sa.select(AiGenerationStageContent).where(
                AiGenerationStageContent.stage_id == attempt.stage_id
            )
        )
        adopted = await CandidateAdoptionApplication(chain_service).adopt(
            requirement_id="req",
            kind="function",
            stage=stage_name,
            actor_id=seeded.actor,
            request=CandidateAdoptRequest(
                action="adopt",
                candidate_id=candidate.candidate_id,
                expected_candidate_token=candidate.candidate_token,
                expected_attempt_id=candidate.current_attempt_id,
                expected_current_token=slot.content_token,
                request_id=uuid4(),
            ),
        )
        return candidate.candidate_id, adopted.content_token


async def submit_relation(sessions, files, seeded, current_token, request_id):
    async with sessions() as session:
        return await CandidateRelations(chain_of(session, files), action="execute").run(
            requirement_id="req",
            current_token=current_token,
            connection_id="llm",
            request_id=request_id,
            actor_id=seeded.actor,
        )


async def test_dispatch_by_an_unknown_connection_is_refused_without_reading_the_document(
    sessions, files, seeded
):
    async with sessions() as session:
        with pytest.raises(AppError):
            await dispatch_of(session, files).run(
                **STAGE,
                request=CandidateRunRequest(connection_id="llm", request_id=uuid4()).model_copy(
                    update={"connection_id": "missing"}
                ),
                actor_id=seeded.actor,
            )

    assert files.storage.calls == 0


async def test_concurrent_dispatches_of_one_request_share_one_attempt(sessions, files, seeded):
    _, runs = await dispatched_twice(sessions, files, seeded)
    async with sessions() as session:
        attempts = await session.scalar(sa.select(sa.func.count()).select_from(AiGenerationAttempt))
        tasks = await session.scalar(sa.select(sa.func.count()).select_from(WorkerTask))

    assert sorted(item.replayed for item in runs) == [False, True]
    assert runs[0].attempt_id == runs[1].attempt_id
    assert attempts == 1
    assert tasks == 1


async def test_dispatch_replays_the_request_without_reading_the_document_again(
    sessions, files, seeded
):
    request, runs = await dispatched_twice(sessions, files, seeded)
    files.storage.fail = True
    calls = files.storage.calls

    replay = await dispatch(sessions, files, seeded.actor, request)

    assert replay.replayed and replay.attempt_id == runs[0].attempt_id
    assert files.storage.calls == calls


async def test_concurrent_revisions_of_the_adopted_material_share_one_attempt(
    sessions, files, seeded
):
    revisions = (await revised_material(sessions, files, seeded)).revisions

    assert sorted(item.replayed for item in revisions) == [False, True]
    assert revisions[0].attempt_id == revisions[1].attempt_id


async def test_a_revision_attaches_its_image_and_derives_from_the_adopted_material(
    sessions, files, seeded
):
    revised = await revised_material(sessions, files, seeded)
    attempt_id = revised.revisions[0].attempt_id
    async with sessions() as session:
        image = await session.scalar(sa.select(StoredFile).where(StoredFile.file_id == "image"))
    await complete(
        sessions, seeded.stage_id, revised.request.request_id, attempt_id, material_artifact()
    )
    derived = await candidate_from(sessions, attempt_id)
    slot = await current_slot(sessions, seeded.stage_id)

    assert image is not None and image.status == "attached"
    assert image.resource_id == attempt_id
    assert derived is not None
    assert derived.derived_from_candidate_id == revised.adopted.adoption.candidate_id
    assert slot.source_candidate_id == revised.adopted.adoption.candidate_id


async def test_a_derived_candidate_is_adoptable_only_while_its_image_belongs_to_its_attempt(
    sessions, files, seeded
):
    state = await derived_material(sessions, files, seeded)
    review = CandidateAdoptRequest(
        action="adopt",
        candidate_id=state.derived.candidate_id,
        expected_candidate_token=state.derived.candidate_token,
        expected_attempt_id=state.derived.current_attempt_id,
        expected_current_token=state.slot.content_token,
        request_id=uuid4(),
    )

    async def preview():
        async with sessions() as session:
            application = CandidateAdoptionApplication(
                generation_services(
                    AiGenerateTaskRepository(session), files=revision_files(session)
                ).chain
            )
            return await application.preview(**STAGE, request=review, actor_id=seeded.actor)

    async def set_image(**values):
        async with sessions() as session:
            await session.execute(
                sa.update(StoredFile).where(StoredFile.file_id == "image").values(**values)
            )
            await session.commit()

    check = await preview()
    await set_image(status="deleting")
    with pytest.raises(AppError, match="来源信息不完整"):
        await preview()
    await set_image(status="attached")
    await set_image(resource_id="another-attempt")
    with pytest.raises(AppError, match="来源信息不完整"):
        await preview()
    await set_image(resource_id=state.attempt_id)

    assert check.can_adopt


async def test_an_auxiliary_launch_fails_when_the_material_changes_while_it_prepares(
    sessions, files, seeded
):
    await adopted_material(sessions, files, seeded)
    await add_task(sessions, seeded, "risk-task", "code_risk_analysis")
    arrived, resume = asyncio.Event(), asyncio.Event()

    class PausedMaterialSource(MaterialSource):
        async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
            arrived.set()
            await asyncio.wait_for(resume.wait(), timeout=10)
            return await super().build_snapshot(task, run_id, worker_id, instruction, **kwargs)

    pending = asyncio.create_task(launch_risk(sessions, files, seeded, PausedMaterialSource()))
    try:
        await asyncio.wait_for(arrived.wait(), timeout=10)
        await replace_slot_token(sessions, seeded.stage_id, "changed-while-preparing")
        resume.set()
        with pytest.raises(AppError) as changed:
            await pending
    finally:
        resume.set()
        await asyncio.gather(pending, return_exceptions=True)
    async with sessions() as session:
        executions = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AiExecution)
            .where(AiExecution.task_id == "risk-task")
        )

    assert changed.value.data["reason"] == "concurrent_change"
    assert executions == 0


async def test_an_auxiliary_launch_freezes_the_material_token_it_read(sessions, files, seeded):
    await adopted_material(sessions, files, seeded)
    await add_task(sessions, seeded, "risk-task", "code_risk_analysis")
    # A rejected launch leaves the replaced token behind; the next launch must freeze that one.
    await replace_slot_token(sessions, seeded.stage_id, "changed-while-preparing")

    result = await launch_risk(sessions, files, seeded, MaterialSource())

    attempt = await attempt_of_execution(sessions, result["runId"])
    assert attempt is not None
    actual = attempt.input_snapshot_json["source"]
    assert actual["requirementMaterialCurrent"]["currentToken"] == "changed-while-preparing"
    assert "requirementMaterialVersion" not in actual


async def test_profile_runs_leave_the_stage_slot_empty(sessions, files, seeded):
    await adopted_material(sessions, files, seeded)
    await add_task(sessions, seeded, "profile-task", "repository_profile")

    first = await create_profile(sessions, files, seeded, "first")
    await create_profile(sessions, files, seeded, "second")

    assert (await current_slot(sessions, first.stage_id)).source_candidate_id is None


async def test_competing_profile_adoptions_have_one_winner_that_replays(sessions, files, seeded):
    await adopted_material(sessions, files, seeded)
    await add_task(sessions, seeded, "profile-task", "repository_profile")
    first = await create_profile(sessions, files, seeded, "first")
    second = await create_profile(sessions, files, seeded, "second")
    empty_token = (await current_slot(sessions, first.stage_id)).content_token
    first_request = profile_adoption(first, empty_token)
    second_request = profile_adoption(second, empty_token)

    competing = await asyncio.wait_for(
        asyncio.gather(
            adopt_profile(sessions, files, seeded, first_request),
            adopt_profile(sessions, files, seeded, second_request),
        ),
        timeout=15,
    )
    winner = first_request if competing[0] is not None else second_request
    replayed = await adopt_profile(sessions, files, seeded, winner)
    await create_profile(sessions, files, seeded, "third")
    current = await current_slot(sessions, first.stage_id)

    assert sum(item is not None for item in competing) == 1
    assert replayed is not None and replayed.replayed
    assert current.source_candidate_id == winner.candidate_id


async def test_ui_dispatch_fails_when_the_profile_changes_during_repository_resolution(
    sessions, files, seeded
):
    await adopted_material(sessions, files, seeded)
    profile = await adopted_profile(sessions, files, seeded)
    await initialize_ui_chain(sessions, files, seeded)
    arrived, resume = asyncio.Event(), asyncio.Event()

    async def resolve_current(**kwargs):
        arrived.set()
        await asyncio.wait_for(resume.wait(), timeout=10)
        return ResolvedUiSource(FROZEN_REPOSITORY, FROZEN_BINDING)

    pending = asyncio.create_task(
        submit_ui(sessions, files, seeded, ui_request(profile.candidate_id), resolve_current)
    )
    try:
        await asyncio.wait_for(arrived.wait(), timeout=10)
        await replace_slot_token(sessions, profile.stage_id, "profile-changed-during-git")
        resume.set()
        with pytest.raises(AppError) as ui_changed:
            await pending
    finally:
        resume.set()
        await asyncio.gather(pending, return_exceptions=True)

    assert ui_changed.value.data["reason"] == "concurrent_change"


async def test_concurrent_ui_dispatches_of_one_request_share_one_attempt(sessions, files, seeded):
    await adopted_material(sessions, files, seeded)
    profile = await adopted_profile(sessions, files, seeded)
    await initialize_ui_chain(sessions, files, seeded)

    async def resolve_current(**kwargs):
        return ResolvedUiSource(FROZEN_REPOSITORY, FROZEN_BINDING)

    request = ui_request(profile.candidate_id)
    runs = await asyncio.wait_for(
        asyncio.gather(
            submit_ui(sessions, files, seeded, request, resolve_current),
            submit_ui(sessions, files, seeded, request, resolve_current),
        ),
        timeout=15,
    )

    assert sorted(result.replayed for result in runs) == [False, True]
    assert runs[0].attempt_id == runs[1].attempt_id


async def test_concurrent_relation_runs_of_one_request_share_one_attempt(sessions, files, seeded):
    await adopted_material(sessions, files, seeded)
    await initialize_function_chain(sessions, files, seeded)
    await create_and_adopt(sessions, files, seeded, "requirement_analysis", scope_artifact())
    await create_and_adopt(sessions, files, seeded, "case_names", points_artifact())
    _, leaf_token = await create_and_adopt(
        sessions, files, seeded, "detailed_cases", CASES_YAML, "yaml"
    )
    request_id = uuid4()

    runs = await asyncio.wait_for(
        asyncio.gather(
            submit_relation(sessions, files, seeded, leaf_token, request_id),
            submit_relation(sessions, files, seeded, leaf_token, request_id),
        ),
        timeout=15,
    )

    assert sorted(result["replayed"] for result in runs) == [False, True]
    assert runs[0]["attemptId"] == runs[1]["attemptId"]


async def test_a_second_leaf_resets_the_graph_while_the_first_run_still_replays(
    sessions, files, seeded
):
    await adopted_material(sessions, files, seeded)
    await initialize_function_chain(sessions, files, seeded)
    await create_and_adopt(sessions, files, seeded, "requirement_analysis", scope_artifact())
    await create_and_adopt(sessions, files, seeded, "case_names", points_artifact())
    first_leaf, leaf_token = await create_and_adopt(
        sessions, files, seeded, "detailed_cases", CASES_YAML, "yaml"
    )
    request_id = uuid4()
    runs = await asyncio.wait_for(
        asyncio.gather(
            submit_relation(sessions, files, seeded, leaf_token, request_id),
            submit_relation(sessions, files, seeded, leaf_token, request_id),
        ),
        timeout=15,
    )
    graph_attempt = await attempt_of(sessions, runs[0]["attemptId"])
    await complete(sessions, graph_attempt.stage_id, request_id, graph_attempt.id, GRAPH)

    second_leaf, second_token = await create_and_adopt(
        sessions, files, seeded, "detailed_cases", CASES_YAML, "yaml"
    )
    async with sessions() as session:
        other_graph = await CandidateRelations(chain_of(session, files), action="read").view(
            requirement_id="req", current_token=second_token, actor_id=seeded.actor
        )
    again = await submit_relation(sessions, files, seeded, leaf_token, request_id)

    assert first_leaf != second_leaf
    assert other_graph["status"] == "not_started" and other_graph["caseRelations"] is None
    assert again["replayed"]
