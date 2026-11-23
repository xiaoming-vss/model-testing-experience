"""Authorized generation passes only verified server-owned candidate sources."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation import generation_services
from support.generation_source_seed import seed_graph
from support.requirement_versions import material_artifact, points_artifact, scope_artifact

from testing_agent.core.errors import AppError
from testing_agent.domain.api_interface import path_key
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateRunRequest,
    CurrentImportRequest,
    SourceSelection,
)
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication
from testing_agent.services.generation_candidate_relation_source import (
    lock_candidate_relation_source,
)
from testing_agent.services.generation_candidate_relations import CandidateRelations
from testing_agent.services.generation_dispatch_application import CandidateDispatchApplication
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_import_application import CurrentImportApplication
from testing_agent.services.repository_profile_adoption import RepositoryProfileAdoption
from testing_agent.services.repository_profile_current import RepositoryProfileCurrent
from testing_agent.services.requirement_material_source import (
    material_reference_fields,
    material_source,
)
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.stage_storage.worker_events import validate_relation_output


class Storage:
    def __init__(self, data):
        self.data = data
        self.calls = 0
        self.fail = False

    def get_object(self, key):
        self.calls += 1
        assert not self.fail and key == "document"
        return {"Body": self}

    def iter_chunks(self, chunk_size):
        yield self.data

    def close(self):
        pass


def configure_document(sync):
    data = b"verified document"
    digest = sha256(data).hexdigest()
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type, requirement.document_file_id = "docx", "document"
    requirement.document_filename, requirement.document_hash = "requirement.docx", digest
    sync.add(
        StoredFile(
            file_id="document",
            project_id="p",
            uploaded_by="u",
            filename="requirement.docx",
            content_type="application/octet-stream",
            size=len(data),
            sha256=digest,
            bucket="bucket",
            object_key="document",
            staging_key="",
            status="attached",
            purpose="requirement",
            resource_type="requirement",
            resource_id="req",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    sync.commit()
    storage = Storage(data)
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)
    return storage, files


def add_slots(sync):
    sync.add(AiGenerationStage(id="stage-d", task_id="task", stage="detailed_cases"))
    sync.flush()
    for key, chain, stage in (
        ("m", "material-chain", "extracting_text"),
        ("a", "function-chain", "requirement_analysis"),
        ("p", "function-chain", "case_names"),
        ("d", "function-chain", "detailed_cases"),
    ):
        sync.add(
            AiGenerationStageContent(
                stage_id=f"stage-{key}", chain_id=chain, stage=stage, content_token=f"empty-{key}"
            )
        )
    sync.commit()


def selection(candidate, kind, stage):
    return SourceSelection(
        chain_kind=kind,
        stage=stage,
        source_kind="candidate",
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        expected_candidate_token=candidate.candidate_token,
    )


async def test_material_to_function_trial_and_stepwise_adoption(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    add_slots(sync)
    storage, files = configure_document(sync)
    session = AsyncSessionAdapter(sync)
    chain = generation_services(AiGenerateTaskRepository(session), files=files).chain
    dispatch = CandidateDispatchApplication(chain)
    adoption = CandidateAdoptionApplication(chain)

    async def launch(kind, stage, selections=(), mode="trial"):
        request = CandidateRunRequest(
            connection_id="llm",
            request_id=uuid4(),
            generation_mode=mode,
            source_selections=list(selections),
        )
        result = await dispatch.run(
            requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
        )
        return request, result

    async def complete(stage_id, request, result, output, fmt="json"):
        await StageWorkerTransitions(session).completed(
            stage_id,
            result.attempt_id,
            str(request.request_id),
            content=json.dumps(output, ensure_ascii=False) if fmt == "json" else output,
            output_format=fmt,
            output_context=None,
        )
        sync.commit()
        return (
            sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=result.attempt_id).one()
        )

    with pytest.raises(AppError) as denied:
        await dispatch.run(
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=CandidateRunRequest(connection_id="llm", request_id=uuid4()),
            actor_id="other",
        )
    assert denied.value.http_code == 403 and storage.calls == 0
    material_req, material_run = await launch(
        "requirement_analysis", "extracting_text", mode="current"
    )
    saved_source = (
        sync.query(AiGenerationAttempt)
        .filter_by(id=material_run.attempt_id)
        .one()
        .input_snapshot_json
    )
    assert saved_source["source"]["documentFileId"] == "document"
    calls = storage.calls
    storage.fail = True
    replay = await dispatch.run(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=material_req,
        actor_id="u",
    )
    assert (
        replay.replayed and replay.attempt_id == material_run.attempt_id and storage.calls == calls
    )
    storage.fail = False
    material = await complete("stage-m", material_req, material_run, material_artifact())
    with pytest.raises(AppError) as blocked:
        await launch("function", "requirement_analysis", mode="current")
    assert blocked.value.data["reason"] == "pending_upstream"
    assert (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one().source_candidate_id
        is None
    )
    analysis_req, analysis_run = await launch(
        "function",
        "requirement_analysis",
        [selection(material, "requirement_analysis", "extracting_text")],
    )
    analysis_input = (
        sync.query(AiGenerationAttempt)
        .filter_by(id=analysis_run.attempt_id)
        .one()
        .input_snapshot_json
    )
    assert json.loads(analysis_input["source"]["sourceContent"]) == material_artifact()
    assert len(analysis_input["candidateInput"]["selectedSources"]) == 1
    analysis = await complete("stage-a", analysis_req, analysis_run, scope_artifact())
    points_req, points_run = await launch(
        "function", "case_names", [selection(analysis, "function", "requirement_analysis")]
    )
    points = await complete("stage-p", points_req, points_run, points_artifact())
    cases_req, cases_run = await launch(
        "function",
        "detailed_cases",
        [
            selection(analysis, "function", "requirement_analysis"),
            selection(points, "function", "case_names"),
        ],
    )
    cases = await complete(
        "stage-d",
        cases_req,
        cases_run,
        "cases:\n  - case_id: graph-case\n    title: example\n",
        fmt="yaml",
    )
    assert all(
        item.source_candidate_id is None for item in sync.query(AiGenerationStageContent).all()
    )
    for candidate, kind, stage, key in (
        (material, "requirement_analysis", "extracting_text", "m"),
        (analysis, "function", "requirement_analysis", "a"),
        (points, "function", "case_names", "p"),
        (cases, "function", "detailed_cases", "d"),
    ):
        request = CandidateAdoptRequest(
            action="adopt",
            candidate_id=candidate.candidate_id,
            expected_candidate_token=candidate.candidate_token,
            expected_attempt_id=candidate.current_attempt_id,
            expected_current_token=f"empty-{key}",
            request_id=uuid4(),
        )
        assert (
            await adoption.preview(
                requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
            )
        ).can_adopt
        result = await adoption.adopt(
            requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
        )
        assert not result.replayed
    assert sync.query(WorkerTask).count() == 4
    assert (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one().source_candidate_id
        == cases.candidate_id
    )
    importer = CurrentImportApplication(chain, secret="test-only-preview-signing-key-32-bytes")
    current_token = (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one().content_token
    )
    prepared = await prepare_requirement_document(session, requirement_id="req", files=files)
    root = await lock_prepared_requirement_root(session, prepared=prepared)
    graph_source = await lock_candidate_relation_source(
        session,
        requirement_id="req",
        expected_current_token=current_token,
        current_root_hashes={root.key: root.content_hash},
    )
    assert graph_source.cases[0]["case_id"] == "graph-case"
    assert json.loads(graph_source.material) == material_artifact()
    assert graph_source.identity()["candidateId"] == cases.candidate_id
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_candidate_relation_source(
            session,
            requirement_id="req",
            expected_current_token="old",
            current_root_hashes={root.key: root.content_hash},
        )
    await session.rollback()
    relation_reader = CandidateRelations(chain, action="read")
    empty_graph = await relation_reader.view(
        requirement_id="req", current_token=current_token, actor_id="u"
    )
    assert empty_graph["candidateId"] == cases.candidate_id
    assert empty_graph["status"] == "not_started" and empty_graph["caseRelations"] is None
    graph_request_id = uuid4()
    relation_writer = CandidateRelations(chain, action="execute")
    started_graph = await relation_writer.run(
        requirement_id="req",
        current_token=current_token,
        connection_id="llm",
        request_id=graph_request_id,
        actor_id="u",
    )
    assert not started_graph["replayed"]
    assert (
        await relation_reader.view(requirement_id="req", current_token=current_token, actor_id="u")
    )["status"] == "pending"
    storage.fail = True
    replayed_graph = await relation_writer.run(
        requirement_id="req",
        current_token=current_token,
        connection_id="llm",
        request_id=graph_request_id,
        actor_id="u",
    )
    assert replayed_graph == {"attemptId": started_graph["attemptId"], "replayed": True}
    storage.fail = False
    graph_attempt = sync.query(AiGenerationAttempt).filter_by(id=started_graph["attemptId"]).one()
    graph_output = {"schema_version": "2.0", "main_paths": [], "edges": []}
    graph_content = validate_relation_output(
        graph_attempt.input_snapshot_json["config"], {"caseRelations": graph_output}
    )
    await StageWorkerTransitions(session).completed(
        graph_attempt.stage_id,
        graph_attempt.id,
        str(graph_request_id),
        content=graph_content,
        output_format="json",
        output_context=None,
    )
    await session.commit()
    finished_graph = await relation_reader.view(
        requirement_id="req", current_token=current_token, actor_id="u"
    )
    assert finished_graph["status"] == "success" and finished_graph["caseRelations"] == graph_output
    other_req, other_run = await launch(
        "function",
        "detailed_cases",
        [
            selection(analysis, "function", "requirement_analysis"),
            selection(points, "function", "case_names"),
        ],
    )
    other_cases = await complete(
        "stage-d",
        other_req,
        other_run,
        "cases:\n  - case_id: graph-case\n    title: example\n",
        fmt="yaml",
    )
    switch = await adoption.adopt(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        actor_id="u",
        request=CandidateAdoptRequest(
            action="adopt",
            candidate_id=other_cases.candidate_id,
            expected_candidate_token=other_cases.candidate_token,
            expected_attempt_id=other_cases.current_attempt_id,
            expected_current_token=current_token,
            request_id=uuid4(),
        ),
    )
    other_graph = await relation_reader.view(
        requirement_id="req", current_token=switch.content_token, actor_id="u"
    )
    assert other_graph["status"] == "not_started" and other_graph["caseRelations"] is None
    restored = await adoption.adopt(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        actor_id="u",
        request=CandidateAdoptRequest(
            action="adopt",
            candidate_id=cases.candidate_id,
            expected_candidate_token=cases.candidate_token,
            expected_attempt_id=cases.current_attempt_id,
            expected_current_token=switch.content_token,
            request_id=uuid4(),
        ),
    )
    current_token = restored.content_token
    assert (
        await relation_reader.view(requirement_id="req", current_token=current_token, actor_id="u")
    )["caseRelations"] == graph_output
    preview = await importer.preview(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token=current_token,
        target_id="",
        actor_id="u",
        now=100,
    )
    assert not preview.requires_confirmation
    imported = await importer.execute(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        actor_id="u",
        now=101,
        request=CurrentImportRequest(
            expected_current_token=preview.current_token,
            expected_lineage_hash=preview.full_lineage_hash,
            preview_token=preview.preview_token,
            request_id=uuid4(),
        ),
    )
    assert (
        imported["imported"]
        and sync.query(FunctionTestCase).filter_by(title="example").count() == 1
    )

    for task_id, task_type in (
        ("profile-task", "repository_profile"),
        ("risk-task", "code_risk_analysis"),
    ):
        sync.add(
            AiGenerateTask(
                task_id=task_id,
                task_type=task_type,
                name=task_id,
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                creator_user_id="u",
                source_type="text",
                source_content="",
            )
        )
    sync.commit()

    class AuxiliarySource:
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

    auxiliary = generation_services(
        AiGenerateTaskRepository(session),
        files=files,
        code_risk_analysis_service=AuxiliarySource(),
        repository_profile_service=AuxiliarySource(),
    ).launcher
    reads_before_denial = storage.calls
    with pytest.raises(AppError) as unauthorized:
        await auxiliary.launch(
            "repository_profile", "profile-task", {"connectionId": "llm"}, "other"
        )
    assert unauthorized.value.http_code == 403 and storage.calls == reads_before_denial
    for kind, task_id in (
        ("repository_profile", "profile-task"),
        ("code_risk_analysis", "risk-task"),
    ):
        run = await auxiliary.launch(kind, task_id, {"connectionId": "llm"}, "u")
        attempt = sync.query(AiGenerationAttempt).filter_by(execution_id=run["runId"]).one()
        actual_source = attempt.input_snapshot_json["source"]
        assert json.loads(actual_source["requirement"]["documentContent"]) == material_artifact()
        assert actual_source["requirementMaterialCurrent"]["candidateId"] == material.candidate_id
        assert "requirementMaterialVersion" not in actual_source
        if kind == "repository_profile":
            first_profile_attempt = attempt.id
            stage_row = sync.query(AiGenerationStage).filter_by(task_id=task_id).one()
            await StageWorkerTransitions(session).completed(
                stage_row.id,
                attempt.id,
                attempt.worker_task_id,
                content=json.dumps({"repositories": [], "overallSummary": "profile"}),
                output_format="json",
                output_context=None,
            )
            sync.commit()
            profile_slot = (
                sync.query(AiGenerationStageContent).filter_by(stage_id=stage_row.id).one()
            )
            empty_profile_token = profile_slot.content_token
            assert profile_slot.source_candidate_id is None

    second_profile = await auxiliary.launch(
        "repository_profile", "profile-task", {"connectionId": "llm"}, "u"
    )
    profile_stage = sync.query(AiGenerationStage).filter_by(task_id="profile-task").one()
    second_attempt = (
        sync.query(AiGenerationAttempt).filter_by(execution_id=second_profile["runId"]).one()
    )
    await StageWorkerTransitions(session).completed(
        profile_stage.id,
        second_attempt.id,
        second_attempt.worker_task_id,
        content=json.dumps({"repositories": [], "overallSummary": "another profile"}),
        output_format="json",
        output_context=None,
    )
    sync.commit()
    assert sync.query(AiGenerationCandidate).filter_by(stage_id=profile_stage.id).count() == 2
    profile_slot = sync.query(AiGenerationStageContent).filter_by(stage_id=profile_stage.id).one()
    assert (
        profile_slot.source_candidate_id is None
        and profile_slot.content_token == empty_profile_token
    )

    first_profile_candidate = (
        sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=first_profile_attempt).one()
    )
    second_profile_candidate = (
        sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=second_attempt.id).one()
    )
    profile_review = RepositoryProfileAdoption(chain)
    profile_request = CandidateAdoptRequest(
        action="adopt",
        candidate_id=first_profile_candidate.candidate_id,
        expected_candidate_token=first_profile_candidate.candidate_token,
        expected_attempt_id=first_profile_candidate.current_attempt_id,
        expected_current_token=empty_profile_token,
        request_id=uuid4(),
    )
    adopted_profile = await profile_review.adopt(
        requirement_id="req", request=profile_request, actor_id="u"
    )
    assert not adopted_profile.replayed
    assert (
        await profile_review.adopt(requirement_id="req", request=profile_request, actor_id="u")
    ).replayed
    profile_slot = sync.query(AiGenerationStageContent).filter_by(stage_id=profile_stage.id).one()
    assert profile_slot.source_candidate_id == first_profile_candidate.candidate_id
    profile_reader = RepositoryProfileCurrent(chain)
    verified_profile = await profile_reader.read(requirement_id="req", actor_id="u")
    assert verified_profile is not None
    stale_request = CandidateAdoptRequest(
        action="adopt",
        candidate_id=second_profile_candidate.candidate_id,
        expected_candidate_token=second_profile_candidate.candidate_token,
        expected_attempt_id=second_profile_candidate.current_attempt_id,
        expected_current_token=empty_profile_token,
        request_id=uuid4(),
    )
    with pytest.raises(AppError) as stale:
        await profile_review.adopt(requirement_id="req", request=stale_request, actor_id="u")
    assert stale.value.data["reason"] == "concurrent_change"
    assert (
        sync.query(AiGenerationStageContent)
        .filter_by(stage_id=profile_stage.id)
        .one()
        .source_candidate_id
        == first_profile_candidate.candidate_id
    )

    sync.add(
        AiGenerateTask(
            task_id="race-risk-task",
            task_type="code_risk_analysis",
            name="race-risk",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="",
        )
    )
    sync.commit()

    class ChangingAuxiliarySource(AuxiliarySource):
        async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
            result = await super().build_snapshot(task, run_id, worker_id, instruction, **kwargs)
            slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
            slot.content_token = "changed-during-remote-preparation"
            sync.commit()
            return result

    racing = generation_services(
        AiGenerateTaskRepository(session),
        files=files,
        code_risk_analysis_service=ChangingAuxiliarySource(),
    ).launcher
    with pytest.raises(AppError) as concurrent:
        await racing.launch("code_risk_analysis", "race-risk-task", {"connectionId": "llm"}, "u")
    assert concurrent.value.data["reason"] == "concurrent_change"
    sync.rollback()
    assert not sync.query(AiGenerationStage).filter_by(task_id="race-risk-task").count()
    aligned_request = stale_request.model_copy(
        update={"request_id": uuid4(), "expected_current_token": adopted_profile.content_token}
    )
    switched_profile = await profile_review.adopt(
        requirement_id="req", request=aligned_request, actor_id="u"
    )
    assert not switched_profile.replayed
    prepared = await prepare_requirement_document(session, requirement_id="req", files=files)
    root = await lock_prepared_requirement_root(session, prepared=prepared)
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await profile_reader.lock_verified(
            requirement_id="req",
            document_root=root,
            source_id=verified_profile.candidate_id,
            expected=verified_profile,
        )
    await session.rollback()

    material_request, material_run = await launch(
        "requirement_analysis", "extracting_text", mode="current"
    )
    other_material = await complete("stage-m", material_request, material_run, material_artifact())
    material_replacement = CandidateAdoptRequest(
        action="adopt",
        candidate_id=other_material.candidate_id,
        expected_candidate_token=other_material.candidate_token,
        expected_attempt_id=other_material.current_attempt_id,
        expected_current_token="changed-during-remote-preparation",
        request_id=uuid4(),
    )
    await adoption.adopt(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=material_replacement,
        actor_id="u",
    )
    current_graph = await relation_reader.view(
        requirement_id="req", current_token=current_token, actor_id="u"
    )
    assert current_graph["status"] == "success"
    old_profile = profile_request.model_copy(
        update={"request_id": uuid4(), "expected_current_token": switched_profile.content_token}
    )
    switched_back = await profile_review.adopt(
        requirement_id="req", request=old_profile, actor_id="u"
    )
    assert not switched_back.replayed
    assert (
        sync.query(AiGenerationStageContent)
        .filter_by(stage_id=profile_stage.id)
        .one()
        .source_candidate_id
        == first_profile_candidate.candidate_id
    )


async def test_api_generation_projects_only_locked_interfaces(database):  # noqa: F811
    sync, _, _ = database
    sync.add(
        AiGenerateTask(
            task_id="api-task",
            task_type="api_case_generate",
            name="api",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="forged",
            interface_ids_json=["interface"],
        )
    )
    sync.flush()
    sync.add(
        RequirementGenerationChain(
            chain_id="api-chain", requirement_id="req", kind="api", task_id="api-task"
        )
    )
    sync.add(AiGenerationStage(id="api-stage", task_id="api-task", stage="interface_extract"))
    sync.add(AiGenerationStage(id="api-design", task_id="api-task", stage="api_design"))
    sync.add(AiGenerationStage(id="api-generate", task_id="api-task", stage="generate"))
    sync.flush()
    for stage_id, stage_name in (
        ("api-stage", "interface_extract"),
        ("api-design", "api_design"),
        ("api-generate", "generate"),
    ):
        sync.add(
            AiGenerationStageContent(
                stage_id=stage_id,
                chain_id="api-chain",
                stage=stage_name,
                content_token=f"empty-{stage_id}",
            )
        )
    sync.add(
        SoftwareRepository(
            software_repository_id="repo",
            project_id="p",
            name="API",
            base_path="/v1",
            repository_instance_url="https://git.example",
            repository_path="group/repo",
            created_by_user_id="u",
        )
    )
    sync.flush()
    sync.add(
        ApiInterface(
            interface_id="interface",
            software_repository_id="repo",
            name="API",
            method="GET",
            path="/x",
            path_key=path_key("/x"),
        )
    )
    sync.commit()
    session = AsyncSessionAdapter(sync)
    app = CandidateDispatchApplication(generation_services(AiGenerateTaskRepository(session)).chain)
    request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        instruction="只处理选中的接口",
        config_json={"maxCases": 8},
    )
    run = await app.run(
        requirement_id="req", kind="api", stage="interface_extract", request=request, actor_id="u"
    )
    replay = await app.run(
        requirement_id="req", kind="api", stage="interface_extract", request=request, actor_id="u"
    )
    assert replay.replayed and replay.attempt_id == run.attempt_id
    assert sync.query(AiGenerationAttempt).filter_by(stage_id="api-stage").count() == 1
    assert sync.query(WorkerTask).filter_by(task_id=str(request.request_id)).count() == 1
    with pytest.raises(AppError, match="正在运行"):
        await app.run(
            requirement_id="req",
            kind="api",
            stage="interface_extract",
            request=request.model_copy(update={"request_id": uuid4()}),
            actor_id="u",
        )
    sync.rollback()
    snapshot = (
        sync.query(AiGenerationAttempt).filter_by(id=run.attempt_id).one().input_snapshot_json
    )
    assert snapshot["source"]["interfaces"][0]["interfaceId"] == "interface"
    assert snapshot["source"]["interfaces"][0]["fullPath"] == "/v1/x"
    assert snapshot["source"]["instruction"] == "只处理选中的接口"
    assert snapshot["config"]["maxCases"] == 8
    assert "forged" not in str(snapshot) and snapshot["candidateProtocol"] == "single-current/1"

    async def complete(stage_id, started, body, output):
        await StageWorkerTransitions(session).completed(
            stage_id,
            started.attempt_id,
            str(body.request_id),
            content=json.dumps(output),
            output_format="json",
            output_context=None,
        )
        sync.commit()
        return (
            sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=started.attempt_id).one()
        )

    extraction = {"endpoint": {"path": "/v1/x", "method": "GET"}}
    first = await complete("api-stage", run, request, extraction)
    next_request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
    next_run = await app.run(
        requirement_id="req",
        kind="api",
        stage="interface_extract",
        request=next_request,
        actor_id="u",
    )
    second = await complete("api-stage", next_run, next_request, extraction)
    design_request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial",
        source_selections=[selection(first, "api", "interface_extract")],
    )
    design_run = await app.run(
        requirement_id="req", kind="api", stage="api_design", request=design_request, actor_id="u"
    )
    design = await complete(
        "api-design",
        design_run,
        design_request,
        {
            "schemaVersion": "api_test_design/1.0",
            "interfaces": {
                "endpoint": {
                    "method": "GET",
                    "path": "/v1/x",
                    "cases": [
                        {
                            "id": "positive",
                            "title": "endpoint positive",
                            "basis": {"kind": "positive"},
                            "expected": {"statusClass": "2xx"},
                        }
                    ],
                    "uncovered": [],
                }
            },
        },
    )
    mismatched = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial",
        source_selections=[
            selection(second, "api", "interface_extract"),
            selection(design, "api", "api_design"),
        ],
    )
    with pytest.raises(AppError) as blocked:
        await app.run(
            requirement_id="req", kind="api", stage="generate", request=mismatched, actor_id="u"
        )
    assert blocked.value.data["reason"] == "source_conflict"
    matched = mismatched.model_copy(
        update={
            "request_id": uuid4(),
            "source_selections": [
                selection(first, "api", "interface_extract"),
                selection(design, "api", "api_design"),
            ],
        }
    )
    final = await app.run(
        requirement_id="req", kind="api", stage="generate", request=matched, actor_id="u"
    )
    final_snapshot = (
        sync.query(AiGenerationAttempt).filter_by(id=final.attempt_id).one().input_snapshot_json
    )
    assert final_snapshot["config"]["apiExtraction"] == extraction
    assert final_snapshot["config"]["apiDesign"]["schemaVersion"] == "api_test_design/1.0"
    assert all(
        slot.source_candidate_id is None
        for slot in sync.query(AiGenerationStageContent).filter_by(chain_id="api-chain")
    )
    review = CandidateAdoptionApplication(app.chain)

    def adoption_request(candidate, stage_id):
        return CandidateAdoptRequest(
            action="adopt",
            candidate_id=candidate.candidate_id,
            expected_candidate_token=candidate.candidate_token,
            expected_attempt_id=candidate.current_attempt_id,
            expected_current_token=f"empty-{stage_id}",
            request_id=uuid4(),
        )

    design_adoption = adoption_request(design, "api-design")
    preflight = await review.preview(
        requirement_id="req",
        kind="api",
        stage="api_design",
        request=design_adoption,
        actor_id="u",
    )
    assert preflight.can_adopt and not preflight.blocking_sources
    await review.adopt(
        requirement_id="req",
        kind="api",
        stage="api_design",
        request=design_adoption,
        actor_id="u",
    )
    assert (
        sync.query(AiGenerationStageContent)
        .filter_by(stage_id="api-design")
        .one()
        .source_candidate_id
        == design.candidate_id
    )
    await review.adopt(
        requirement_id="req",
        kind="api",
        stage="interface_extract",
        request=adoption_request(first, "api-stage"),
        actor_id="u",
    )
