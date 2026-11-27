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
from support.memory_storage import Storage
from support.requirement_versions import (
    candidate_selection,
    material_artifact,
    points_artifact,
    scope_artifact,
)

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

SECRET = "test-only-preview-signing-key-32-bytes"
CASES_YAML = "cases:\n  - case_id: graph-case\n    title: example\n"
GRAPH_OUTPUT = {"schema_version": "2.0", "main_paths": [], "edges": []}
EXTRACTION = {"endpoint": {"path": "/v1/x", "method": "GET"}}
DESIGN = {
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
}


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


def slot(sync, stage_id):
    """The current slot of a stage."""
    return sync.query(AiGenerationStageContent).filter_by(stage_id=stage_id).one()


def attempt(sync, attempt_id):
    return sync.query(AiGenerationAttempt).filter_by(id=attempt_id).one()


def candidate_of(sync, origin_attempt):
    return sync.query(AiGenerationCandidate).filter_by(origin_attempt_id=origin_attempt.id).one()


def adopt_request(candidate, key):
    """Adopt ``candidate`` while its stage slot still carries the ``empty-<key>`` token."""
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=candidate.candidate_id,
        expected_candidate_token=candidate.candidate_token,
        expected_attempt_id=candidate.current_attempt_id,
        expected_current_token=f"empty-{key}",
        request_id=uuid4(),
    )


class AuxiliarySource:
    """Snapshot builder of repository-profile and code-risk runs: the adopted material."""

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


def add_auxiliary_tasks(sync, *tasks):
    """Add ``(task_id, task_type)`` auxiliary tasks of requirement ``req``."""
    for task_id, task_type in tasks:
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


@pytest.fixture
def generation(database):  # noqa: F811
    """Seeded graph with empty stage slots, a stored document and the applications."""
    sync, _, _ = database
    seed_graph(sync)
    add_slots(sync)
    storage, files = configure_document(sync)
    session = AsyncSessionAdapter(sync)
    chain = generation_services(AiGenerateTaskRepository(session), files=files).chain
    return SimpleNamespace(
        sync=sync,
        session=session,
        files=files,
        storage=storage,
        chain=chain,
        dispatch=CandidateDispatchApplication(chain),
        adoption=CandidateAdoptionApplication(chain),
    )


async def launch(generation, kind, stage, selections=(), mode="trial"):
    """Run ``stage`` as "u"; returns the request and the run."""
    request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode=mode,
        source_selections=list(selections),
    )
    result = await generation.dispatch.run(
        requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
    )
    return request, result


async def complete(generation, stage_id, request, result, output, fmt="json"):
    """Complete ``result`` with ``output``; returns the candidate it produces."""
    await StageWorkerTransitions(generation.session).completed(
        stage_id,
        result.attempt_id,
        str(request.request_id),
        content=json.dumps(output, ensure_ascii=False) if fmt == "json" else output,
        output_format=fmt,
        output_context=None,
    )
    generation.sync.commit()
    return (
        generation.sync.query(AiGenerationCandidate)
        .filter_by(origin_attempt_id=result.attempt_id)
        .one()
    )


async def current_material(generation):
    """Extract the text of the current document; returns the material candidate."""
    request, run = await launch(
        generation, "requirement_analysis", "extracting_text", mode="current"
    )
    return await complete(generation, "stage-m", request, run, material_artifact())


async def trial_branch(generation, material):
    """Generate analysis, test points and cases as trials of ``material``; adopts nothing."""
    request, run = await launch(
        generation,
        "function",
        "requirement_analysis",
        [candidate_selection(material, "requirement_analysis", "extracting_text")],
    )
    analysis = await complete(generation, "stage-a", request, run, scope_artifact())
    request, run = await launch(
        generation,
        "function",
        "case_names",
        [candidate_selection(analysis, "function", "requirement_analysis")],
    )
    points = await complete(generation, "stage-p", request, run, points_artifact())
    request, run = await launch(
        generation,
        "function",
        "detailed_cases",
        [
            candidate_selection(analysis, "function", "requirement_analysis"),
            candidate_selection(points, "function", "case_names"),
        ],
    )
    cases = await complete(generation, "stage-d", request, run, CASES_YAML, fmt="yaml")
    return SimpleNamespace(material=material, analysis=analysis, points=points, cases=cases)


async def adopt(generation, candidate, kind, stage, key):
    return await generation.adoption.adopt(
        requirement_id="req",
        kind=kind,
        stage=stage,
        request=adopt_request(candidate, key),
        actor_id="u",
    )


async def adopted_branch(generation):
    """Generate the trial branch of the current material and adopt its four candidates."""
    branch = await trial_branch(generation, await current_material(generation))
    for candidate, kind, stage, key in (
        (branch.material, "requirement_analysis", "extracting_text", "m"),
        (branch.analysis, "function", "requirement_analysis", "a"),
        (branch.points, "function", "case_names", "p"),
        (branch.cases, "function", "detailed_cases", "d"),
    ):
        await adopt(generation, candidate, kind, stage, key)
    return branch


async def adopt_cases(generation, candidate, expected_current_token):
    """Make ``candidate`` the current detailed cases; returns the adoption result."""
    return await generation.adoption.adopt(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        actor_id="u",
        request=CandidateAdoptRequest(
            action="adopt",
            candidate_id=candidate.candidate_id,
            expected_candidate_token=candidate.candidate_token,
            expected_attempt_id=candidate.current_attempt_id,
            expected_current_token=expected_current_token,
            request_id=uuid4(),
        ),
    )


async def relation_view(generation, current_token):
    """What a user sees of the relation graph of the current cases."""
    reader = CandidateRelations(generation.chain, action="read")
    return await reader.view(requirement_id="req", current_token=current_token, actor_id="u")


async def start_relation_graph(generation, current_token):
    """Start the relation run of the adopted cases; returns its request id and run."""
    request_id = uuid4()
    started = await CandidateRelations(generation.chain, action="execute").run(
        requirement_id="req",
        current_token=current_token,
        connection_id="llm",
        request_id=request_id,
        actor_id="u",
    )
    return request_id, started


async def publish_relation_graph(generation, request_id, started):
    """Complete the relation run with a valid empty graph; returns the validated content."""
    graph_attempt = attempt(generation.sync, started["attemptId"])
    content = validate_relation_output(
        graph_attempt.input_snapshot_json["config"], {"caseRelations": GRAPH_OUTPUT}
    )
    await StageWorkerTransitions(generation.session).completed(
        graph_attempt.stage_id,
        graph_attempt.id,
        str(request_id),
        content=content,
        output_format="json",
        output_context=None,
    )
    await generation.session.commit()
    return content


def profile_launcher(generation):
    """Launcher whose auxiliary runs take the adopted material as their source."""
    return generation_services(
        AiGenerateTaskRepository(generation.session),
        files=generation.files,
        code_risk_analysis_service=AuxiliarySource(),
        repository_profile_service=AuxiliarySource(),
    ).launcher


async def run_profile(generation, launcher, summary):
    """Run the repository-profile task and complete it; returns its attempt and stage."""
    run = await launcher.launch("repository_profile", "profile-task", {"connectionId": "llm"}, "u")
    stage = generation.sync.query(AiGenerationStage).filter_by(task_id="profile-task").one()
    attempt_row = (
        generation.sync.query(AiGenerationAttempt).filter_by(execution_id=run["runId"]).one()
    )
    await StageWorkerTransitions(generation.session).completed(
        stage.id,
        attempt_row.id,
        attempt_row.worker_task_id,
        content=json.dumps({"repositories": [], "overallSummary": summary}),
        output_format="json",
        output_context=None,
    )
    generation.sync.commit()
    return attempt_row, stage


def adoption_request(candidate, expected_current_token):
    """Adopt ``candidate`` while the slot token is ``expected_current_token``."""
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=candidate.candidate_id,
        expected_candidate_token=candidate.candidate_token,
        expected_attempt_id=candidate.current_attempt_id,
        expected_current_token=expected_current_token,
        request_id=uuid4(),
    )


async def test_dispatch_by_another_actor_is_refused_without_reading_the_document(generation):
    with pytest.raises(AppError) as denied:
        await generation.dispatch.run(
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=CandidateRunRequest(connection_id="llm", request_id=uuid4()),
            actor_id="other",
        )

    assert denied.value.http_code == 403
    assert generation.storage.calls == 0


async def test_material_run_replays_without_reading_the_document_again(generation):
    request, run = await launch(
        generation, "requirement_analysis", "extracting_text", mode="current"
    )
    saved = attempt(generation.sync, run.attempt_id).input_snapshot_json
    reads = generation.storage.calls
    generation.storage.fail = True

    replay = await generation.dispatch.run(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=request,
        actor_id="u",
    )

    assert saved["source"]["documentFileId"] == "document"
    assert replay.replayed and replay.attempt_id == run.attempt_id
    assert generation.storage.calls == reads


async def test_current_mode_waits_for_an_adopted_upstream_slot(generation):
    await current_material(generation)

    with pytest.raises(AppError) as blocked:
        await launch(generation, "function", "requirement_analysis", mode="current")

    assert blocked.value.data["reason"] == "pending_upstream"
    assert slot(generation.sync, "stage-m").source_candidate_id is None


async def test_trial_stage_input_is_the_candidate_it_selects(generation):
    material = await current_material(generation)
    _, run = await launch(
        generation,
        "function",
        "requirement_analysis",
        [candidate_selection(material, "requirement_analysis", "extracting_text")],
    )

    trial_input = attempt(generation.sync, run.attempt_id).input_snapshot_json

    assert json.loads(trial_input["source"]["sourceContent"]) == material_artifact()
    assert len(trial_input["candidateInput"]["selectedSources"]) == 1


async def test_trial_generation_adopts_nothing(generation):
    await trial_branch(generation, await current_material(generation))

    slots = generation.sync.query(AiGenerationStageContent).all()

    assert all(item.source_candidate_id is None for item in slots)


async def test_each_trial_candidate_can_be_adopted_and_queues_one_worker(generation):
    branch = await trial_branch(generation, await current_material(generation))
    preflights, results = [], []
    for candidate, kind, stage, key in (
        (branch.material, "requirement_analysis", "extracting_text", "m"),
        (branch.analysis, "function", "requirement_analysis", "a"),
        (branch.points, "function", "case_names", "p"),
        (branch.cases, "function", "detailed_cases", "d"),
    ):
        request = adopt_request(candidate, key)
        preflights.append(
            await generation.adoption.preview(
                requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
            )
        )
        results.append(await adopt(generation, candidate, kind, stage, key))
    workers = generation.sync.query(WorkerTask).count()

    assert all(preflight.can_adopt for preflight in preflights)
    assert all(not result.replayed for result in results)
    assert workers == 4
    assert slot(generation.sync, "stage-d").source_candidate_id == branch.cases.candidate_id


async def test_relation_source_is_locked_to_the_adopted_cases(generation):
    branch = await adopted_branch(generation)
    prepared = await prepare_requirement_document(
        generation.session, requirement_id="req", files=generation.files
    )
    root = await lock_prepared_requirement_root(generation.session, prepared=prepared)
    current_token = slot(generation.sync, "stage-d").content_token

    graph_source = await lock_candidate_relation_source(
        generation.session,
        requirement_id="req",
        expected_current_token=current_token,
        current_root_hashes={root.key: root.content_hash},
    )
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_candidate_relation_source(
            generation.session,
            requirement_id="req",
            expected_current_token="old",
            current_root_hashes={root.key: root.content_hash},
        )
    await generation.session.rollback()

    assert graph_source.cases[0]["case_id"] == "graph-case"
    assert json.loads(graph_source.material) == material_artifact()
    assert graph_source.identity()["candidateId"] == branch.cases.candidate_id


async def test_relation_run_replays_one_attempt_and_publishes_its_graph(generation):
    branch = await adopted_branch(generation)
    current_token = slot(generation.sync, "stage-d").content_token
    reader = CandidateRelations(generation.chain, action="read")
    before = await reader.view(requirement_id="req", current_token=current_token, actor_id="u")
    request_id, started = await start_relation_graph(generation, current_token)
    pending = await reader.view(requirement_id="req", current_token=current_token, actor_id="u")
    reads = generation.storage.calls
    generation.storage.fail = True
    replayed = await CandidateRelations(generation.chain, action="execute").run(
        requirement_id="req",
        current_token=current_token,
        connection_id="llm",
        request_id=request_id,
        actor_id="u",
    )
    replay_reads = generation.storage.calls
    generation.storage.fail = False
    await publish_relation_graph(generation, request_id, started)
    finished = await reader.view(requirement_id="req", current_token=current_token, actor_id="u")

    assert before["candidateId"] == branch.cases.candidate_id
    assert before["status"] == "not_started" and before["caseRelations"] is None
    assert not started["replayed"]
    assert pending["status"] == "pending"
    assert replayed == {"attemptId": started["attemptId"], "replayed": True}
    assert replay_reads == reads
    assert finished["status"] == "success" and finished["caseRelations"] == GRAPH_OUTPUT


async def test_switching_the_cases_resets_the_relation_graph_and_switching_back_restores_it(
    generation,
):
    branch = await adopted_branch(generation)
    current_token = slot(generation.sync, "stage-d").content_token
    request_id, started = await start_relation_graph(generation, current_token)
    await publish_relation_graph(generation, request_id, started)
    request, run = await launch(
        generation,
        "function",
        "detailed_cases",
        [
            candidate_selection(branch.analysis, "function", "requirement_analysis"),
            candidate_selection(branch.points, "function", "case_names"),
        ],
    )
    other_cases = await complete(generation, "stage-d", request, run, CASES_YAML, fmt="yaml")
    reader = CandidateRelations(generation.chain, action="read")
    switch = await adopt_cases(generation, other_cases, current_token)
    reset = await reader.view(
        requirement_id="req", current_token=switch.content_token, actor_id="u"
    )
    restored = await adopt_cases(generation, branch.cases, switch.content_token)
    back = await reader.view(
        requirement_id="req", current_token=restored.content_token, actor_id="u"
    )

    assert reset["status"] == "not_started" and reset["caseRelations"] is None
    assert back["caseRelations"] == GRAPH_OUTPUT


async def test_adopted_cases_import_without_confirmation(generation):
    await adopted_branch(generation)
    current_token = slot(generation.sync, "stage-d").content_token
    importer = CurrentImportApplication(generation.chain, secret=SECRET)
    preview = await importer.preview(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token=current_token,
        target_id="",
        actor_id="u",
        now=100,
    )

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

    assert not preview.requires_confirmation
    assert imported["imported"]
    assert generation.sync.query(FunctionTestCase).filter_by(title="example").count() == 1


async def test_auxiliary_launch_needs_write_access_and_takes_the_adopted_material(
    generation,
):
    branch = await adopted_branch(generation)
    add_auxiliary_tasks(
        generation.sync, ("profile-task", "repository_profile"), ("risk-task", "code_risk_analysis")
    )
    launcher = profile_launcher(generation)
    reads = generation.storage.calls

    with pytest.raises(AppError) as unauthorized:
        await launcher.launch(
            "repository_profile", "profile-task", {"connectionId": "llm"}, "other"
        )
    reads_after_denial = generation.storage.calls
    sources = []
    for kind, task_id in (
        ("repository_profile", "profile-task"),
        ("code_risk_analysis", "risk-task"),
    ):
        run = await launcher.launch(kind, task_id, {"connectionId": "llm"}, "u")
        attempt_row = (
            generation.sync.query(AiGenerationAttempt).filter_by(execution_id=run["runId"]).one()
        )
        sources.append(attempt_row.input_snapshot_json["source"])

    assert unauthorized.value.http_code == 403
    assert reads_after_denial == reads
    for source in sources:
        assert json.loads(source["requirement"]["documentContent"]) == material_artifact()
        assert source["requirementMaterialCurrent"]["candidateId"] == branch.material.candidate_id
        assert "requirementMaterialVersion" not in source


async def test_each_profile_run_leaves_a_candidate_and_keeps_the_slot_empty(generation):
    await adopted_branch(generation)
    add_auxiliary_tasks(generation.sync, ("profile-task", "repository_profile"))
    launcher = profile_launcher(generation)

    _, stage = await run_profile(generation, launcher, "profile")
    empty = slot(generation.sync, stage.id)
    assert empty.source_candidate_id is None
    _, _ = await run_profile(generation, launcher, "another profile")

    candidates = generation.sync.query(AiGenerationCandidate).filter_by(stage_id=stage.id).count()
    after = slot(generation.sync, stage.id)
    assert candidates == 2
    assert after.source_candidate_id is None and after.content_token == empty.content_token


async def test_profile_adoption_is_idempotent_and_rejects_a_stale_slot_token(generation):
    await adopted_branch(generation)
    add_auxiliary_tasks(generation.sync, ("profile-task", "repository_profile"))
    launcher = profile_launcher(generation)
    first_attempt, stage = await run_profile(generation, launcher, "profile")
    second_attempt, _ = await run_profile(generation, launcher, "another profile")
    first = candidate_of(generation.sync, first_attempt)
    second = candidate_of(generation.sync, second_attempt)
    empty_token = slot(generation.sync, stage.id).content_token
    review = RepositoryProfileAdoption(generation.chain)

    request = adoption_request(first, empty_token)
    adopted = await review.adopt(requirement_id="req", request=request, actor_id="u")
    again = await review.adopt(requirement_id="req", request=request, actor_id="u")
    adopted_slot = slot(generation.sync, stage.id)
    verified = await RepositoryProfileCurrent(generation.chain).read(
        requirement_id="req", actor_id="u"
    )
    with pytest.raises(AppError) as stale:
        await review.adopt(
            requirement_id="req", request=adoption_request(second, empty_token), actor_id="u"
        )

    assert not adopted.replayed
    assert again.replayed
    assert adopted_slot.source_candidate_id == first.candidate_id
    assert verified is not None
    assert stale.value.data["reason"] == "concurrent_change"
    assert slot(generation.sync, stage.id).source_candidate_id == first.candidate_id


async def test_auxiliary_launch_leaves_no_stage_behind_when_the_material_changes_meanwhile(
    generation,
):
    await adopted_branch(generation)
    add_auxiliary_tasks(generation.sync, ("race-risk-task", "code_risk_analysis"))

    class ChangingAuxiliarySource(AuxiliarySource):
        async def build_snapshot(self, task, run_id, worker_id, instruction, **kwargs):
            result = await super().build_snapshot(task, run_id, worker_id, instruction, **kwargs)
            slot(generation.sync, "stage-m").content_token = "changed-during-remote-preparation"
            generation.sync.commit()
            return result

    racing = generation_services(
        AiGenerateTaskRepository(generation.session),
        files=generation.files,
        code_risk_analysis_service=ChangingAuxiliarySource(),
    ).launcher
    with pytest.raises(AppError) as concurrent:
        await racing.launch("code_risk_analysis", "race-risk-task", {"connectionId": "llm"}, "u")
    generation.sync.rollback()

    assert concurrent.value.data["reason"] == "concurrent_change"
    assert not generation.sync.query(AiGenerationStage).filter_by(task_id="race-risk-task").count()


async def test_switching_the_profile_outdates_the_verified_one(generation):
    await adopted_branch(generation)
    add_auxiliary_tasks(generation.sync, ("profile-task", "repository_profile"))
    launcher = profile_launcher(generation)
    first_attempt, stage = await run_profile(generation, launcher, "profile")
    second_attempt, _ = await run_profile(generation, launcher, "another profile")
    first = candidate_of(generation.sync, first_attempt)
    second = candidate_of(generation.sync, second_attempt)
    review = RepositoryProfileAdoption(generation.chain)
    adopted = await review.adopt(
        requirement_id="req",
        request=adoption_request(first, slot(generation.sync, stage.id).content_token),
        actor_id="u",
    )
    verified = await RepositoryProfileCurrent(generation.chain).read(
        requirement_id="req", actor_id="u"
    )

    switched = await review.adopt(
        requirement_id="req",
        request=adoption_request(second, adopted.content_token),
        actor_id="u",
    )
    prepared = await prepare_requirement_document(
        generation.session, requirement_id="req", files=generation.files
    )
    root = await lock_prepared_requirement_root(generation.session, prepared=prepared)
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await RepositoryProfileCurrent(generation.chain).lock_verified(
            requirement_id="req",
            document_root=root,
            source_id=verified.candidate_id,
            expected=verified,
        )
    await generation.session.rollback()

    assert not switched.replayed


async def test_replacing_the_material_keeps_the_relation_graph_of_the_adopted_cases(generation):
    await adopted_branch(generation)
    current_token = slot(generation.sync, "stage-d").content_token
    request_id, started = await start_relation_graph(generation, current_token)
    await publish_relation_graph(generation, request_id, started)
    material_token = slot(generation.sync, "stage-m").content_token

    request, run = await launch(
        generation, "requirement_analysis", "extracting_text", mode="current"
    )
    other_material = await complete(generation, "stage-m", request, run, material_artifact())
    await generation.adoption.adopt(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=adoption_request(other_material, material_token),
        actor_id="u",
    )

    graph = await relation_view(generation, current_token)

    assert graph["status"] == "success"


async def test_the_profile_switches_back_to_an_earlier_candidate(generation):
    await adopted_branch(generation)
    add_auxiliary_tasks(generation.sync, ("profile-task", "repository_profile"))
    launcher = profile_launcher(generation)
    first_attempt, stage = await run_profile(generation, launcher, "profile")
    second_attempt, _ = await run_profile(generation, launcher, "another profile")
    first = candidate_of(generation.sync, first_attempt)
    second = candidate_of(generation.sync, second_attempt)
    review = RepositoryProfileAdoption(generation.chain)
    adopted = await review.adopt(
        requirement_id="req",
        request=adoption_request(first, slot(generation.sync, stage.id).content_token),
        actor_id="u",
    )
    switched = await review.adopt(
        requirement_id="req", request=adoption_request(second, adopted.content_token), actor_id="u"
    )

    switched_back = await review.adopt(
        requirement_id="req", request=adoption_request(first, switched.content_token), actor_id="u"
    )

    assert not switched_back.replayed
    assert slot(generation.sync, stage.id).source_candidate_id == first.candidate_id


@pytest.fixture
def api_generation(database):  # noqa: F811
    """API generation chain with empty slots over one interface of a software repository."""
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
    return SimpleNamespace(
        sync=sync,
        session=session,
        app=CandidateDispatchApplication(
            generation_services(AiGenerateTaskRepository(session)).chain
        ),
    )


async def run_api(generation, stage, request):
    return await generation.app.run(
        requirement_id="req", kind="api", stage=stage, request=request, actor_id="u"
    )


async def complete_api(generation, stage_id, request, run, output):
    await StageWorkerTransitions(generation.session).completed(
        stage_id,
        run.attempt_id,
        str(request.request_id),
        content=json.dumps(output),
        output_format="json",
        output_context=None,
    )
    generation.sync.commit()
    return (
        generation.sync.query(AiGenerationCandidate)
        .filter_by(origin_attempt_id=run.attempt_id)
        .one()
    )


async def extract_interfaces(generation):
    """Extract the interfaces once and complete the run; returns request, run and candidate."""
    request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
    run = await run_api(generation, "interface_extract", request)
    return request, run, await complete_api(generation, "api-stage", request, run, EXTRACTION)


async def design_trial(generation, extraction):
    """Design the API on a trial of ``extraction``; returns the design candidate."""
    request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial",
        source_selections=[candidate_selection(extraction, "api", "interface_extract")],
    )
    run = await run_api(generation, "api_design", request)
    return await complete_api(generation, "api-design", request, run, DESIGN)


def generate_request(extraction, design):
    """Case-generation request on the pair of an extraction and a design candidate."""
    return CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        generation_mode="trial",
        source_selections=[
            candidate_selection(extraction, "api", "interface_extract"),
            candidate_selection(design, "api", "api_design"),
        ],
    )


async def test_api_run_replays_one_request_and_refuses_a_parallel_one(api_generation):
    request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
    run = await run_api(api_generation, "interface_extract", request)
    replay = await run_api(api_generation, "interface_extract", request)
    attempts = (
        api_generation.sync.query(AiGenerationAttempt).filter_by(stage_id="api-stage").count()
    )
    tasks = api_generation.sync.query(WorkerTask).filter_by(task_id=str(request.request_id)).count()
    with pytest.raises(AppError, match="正在运行"):
        await run_api(
            api_generation, "interface_extract", request.model_copy(update={"request_id": uuid4()})
        )
    api_generation.sync.rollback()

    assert replay.replayed and replay.attempt_id == run.attempt_id
    assert attempts == 1
    assert tasks == 1


async def test_api_run_snapshot_projects_only_the_locked_interfaces(api_generation):
    request = CandidateRunRequest(
        connection_id="llm",
        request_id=uuid4(),
        instruction="只处理选中的接口",
        config_json={"maxCases": 8},
    )
    run = await run_api(api_generation, "interface_extract", request)
    api_generation.sync.rollback()

    snapshot = attempt(api_generation.sync, run.attempt_id).input_snapshot_json

    assert snapshot["source"]["interfaces"][0]["interfaceId"] == "interface"
    assert snapshot["source"]["interfaces"][0]["fullPath"] == "/v1/x"
    assert snapshot["source"]["instruction"] == "只处理选中的接口"
    assert snapshot["config"]["maxCases"] == 8
    assert "forged" not in str(snapshot) and snapshot["candidateProtocol"] == "single-current/1"


async def test_api_generate_rejects_sources_from_different_extractions(api_generation):
    _, _, first = await extract_interfaces(api_generation)
    _, _, second = await extract_interfaces(api_generation)
    design = await design_trial(api_generation, first)

    with pytest.raises(AppError) as blocked:
        await run_api(api_generation, "generate", generate_request(second, design))

    assert blocked.value.data["reason"] == "source_conflict"


async def test_api_generate_carries_its_selected_sources_and_adopts_nothing(api_generation):
    _, _, first = await extract_interfaces(api_generation)
    design = await design_trial(api_generation, first)

    final = await run_api(api_generation, "generate", generate_request(first, design))

    snapshot = attempt(api_generation.sync, final.attempt_id).input_snapshot_json
    assert snapshot["config"]["apiExtraction"] == EXTRACTION
    assert snapshot["config"]["apiDesign"]["schemaVersion"] == "api_test_design/1.0"
    assert all(
        item.source_candidate_id is None
        for item in api_generation.sync.query(AiGenerationStageContent).filter_by(
            chain_id="api-chain"
        )
    )


async def test_api_trial_candidates_can_each_be_adopted_into_their_stage(api_generation):
    _, _, first = await extract_interfaces(api_generation)
    design = await design_trial(api_generation, first)
    review = CandidateAdoptionApplication(api_generation.app.chain)
    request = adopt_request(design, "api-design")
    preflight = await review.preview(
        requirement_id="req", kind="api", stage="api_design", request=request, actor_id="u"
    )
    await review.adopt(
        requirement_id="req", kind="api", stage="api_design", request=request, actor_id="u"
    )

    await review.adopt(
        requirement_id="req",
        kind="api",
        stage="interface_extract",
        request=adopt_request(first, "api-stage"),
        actor_id="u",
    )

    assert preflight.can_adopt and not preflight.blocking_sources
    assert slot(api_generation.sync, "api-design").source_candidate_id == design.candidate_id
    assert slot(api_generation.sync, "api-stage").source_candidate_id == first.candidate_id
