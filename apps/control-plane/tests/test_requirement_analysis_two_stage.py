import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from support.execution_writer import MemoryExecutionWriter

from testing_agent.core.errors import AppError
from testing_agent.domain.requirement_artifacts import requirement_content, validate_artifact
from testing_agent.services import ai_stage_workflow as workflow
from testing_agent.services.ai_task_contracts import next_requirement_analysis_stage
from testing_agent.services.ai_task_output import requirement_analysis_import_content
from testing_agent.services.requirement_analysis_contracts import (
    merge_stage_config,
    validate_run_output,
)
from testing_agent.services.worker_task import WorkerTaskService

FIXTURES = Path(__file__).resolve().parent / "fixtures/requirement_artifacts"


def example(name):
    return json.loads((FIXTURES / (name + ".example.json")).read_text())


def run(version=2):
    return SimpleNamespace(
        run_id="run",
        task_id="task",
        project_id="project",
        snapshot_json={"workflowVersion": version},
        checkpoint_enabled=True,
        current_stage="extracting_text",
        stage_status="waiting_review",
        status="waiting_review",
        review_status="pending",
        import_status="pending",
        config_json={"firstStepOutput": example("document-extraction")},
        result_yaml=json.dumps(example("requirement-understanding")),
        result_summary_json={},
    )


def test_import_preserves_complete_structure_and_rejects_retired_version():
    candidate = run()
    imported = requirement_analysis_import_content(candidate)
    assert json.loads(imported) == example("requirement-understanding")
    assert requirement_content(imported) == imported
    legacy = run(1)
    legacy.result_yaml = "历史需求正文"
    with pytest.raises(AppError):
        requirement_analysis_import_content(legacy)


def test_malformed_new_import_cannot_fall_back_to_summary():
    candidate = run()
    candidate.result_yaml = "旧文本"
    candidate.result_summary_json = {"valid": True}
    with pytest.raises(AppError):
        requirement_analysis_import_content(candidate)


def test_cannot_change_approved_extraction_from_understanding_editor():
    candidate = run()
    changed = deepcopy(candidate.config_json)
    changed["firstStepOutput"]["documentTitle"] = "changed"
    with pytest.raises(AppError):
        merge_stage_config(candidate, changed, "feature_understanding")


def test_only_two_stage_transition_is_supported():
    assert next_requirement_analysis_stage("extracting_text") == "feature_understanding"
    assert next_requirement_analysis_stage("writing_requirement") is None
    assert next_requirement_analysis_stage("feature_understanding") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_completed_marker_remains_reviewable_without_creating_another_stage(
    monkeypatch, action
):
    candidate = run()
    candidate.current_stage = "completed"
    candidate.status = "success"
    candidate.stage_status = "completed"

    async def owned(*args, **kwargs):
        return candidate

    async def nothing(*args):
        pass

    monkeypatch.setattr(workflow, "dump_run", lambda value: {"reviewStatus": value.review_status})
    service = workflow.GenerationStageWorkflow(
        repository=SimpleNamespace(session=None, commit=nothing, refresh=nothing),
        owned_run=owned,
        execution_writer=MemoryExecutionWriter(),
    )
    result = await service.review_requirement_analysis_stage(
        "run", {"stage": "feature_understanding", "action": action}, "reviewer"
    )
    assert result["reviewStatus"] == ("approved" if action == "approve" else "rejected")
    assert candidate.reviewer_user_id == "reviewer"


@pytest.mark.asyncio
async def test_extraction_approval_dispatches_understanding_only(monkeypatch):
    candidate, added = run(), []

    async def owned(*args, **kwargs):
        return candidate

    async def commit():
        pass

    async def refresh(value):
        pass

    async def latest(run_id):
        return SimpleNamespace(llm_connection_id="connection")

    async def connection(*args):
        return SimpleNamespace(connection_id="connection")

    monkeypatch.setattr(workflow, "require_personal_connection", connection)
    monkeypatch.setattr(workflow, "dump_run", lambda value: {"currentStage": value.current_stage})
    repository = SimpleNamespace(
        session=None,
        commit=commit,
        refresh=refresh,
        get_latest_ai_dispatch=latest,
        add=added.append,
    )
    service = workflow.GenerationStageWorkflow(
        repository=repository, owned_run=owned, execution_writer=MemoryExecutionWriter()
    )
    result = await service.review_requirement_analysis_stage(
        "run", {"stage": "extracting_text", "action": "approve"}, "user"
    )
    assert result["currentStage"] == "feature_understanding"
    assert len(added) == 1
    assert "secondStepOutput" not in candidate.config_json


def test_invalid_source_and_resolved_question_answer_are_rejected():
    value = example("requirement-understanding")
    value["questions"][0]["status"] = "resolved"
    with pytest.raises(ValueError):
        validate_artifact(value, "requirement_understanding")
    candidate = run()
    candidate.config_json["firstStepOutput"]["extractedFacts"][0]["fact"]["sourceReferences"][0][
        "sourceId"
    ] = "missing"
    with pytest.raises(AppError):
        validate_run_output(candidate)


def test_unknown_module_scope_is_valid_without_placeholder_modules():
    value = example("requirement-understanding")
    value["modules"] = []
    value["businessFlows"] = []
    value["businessRules"] = []
    value["questions"] = [value["questions"][0]]
    value["questions"][0]["question"] = "当前材料未能识别业务范围和模块，请确认。"
    value["questions"][0]["affectedRefs"] = [{"kind": "requirement", "id": "requirement"}]
    value["functionalOverview"] = {
        "purpose": {
            "value": None,
            "confirmationStatus": "unconfirmed",
            "relatedQuestionIds": ["Q01"],
        },
        "scope": [],
        "actors": [],
        "explicitExclusions": [],
    }
    validate_artifact(value, "requirement_understanding")
    value["questions"] = []
    with pytest.raises(ValueError):
        validate_artifact(value, "requirement_understanding")


def test_non_standard_numbers_and_duplicate_keys_cannot_enter_imported_json():
    value = example("requirement-understanding")
    control = value["modules"][0]["operations"][0]["interaction"]["controls"][0]
    control["defaultValue"] = {"value": float("nan"), "confirmationStatus": "unconfirmed"}
    with pytest.raises(ValueError):
        validate_artifact(value, "requirement_understanding")
    with pytest.raises(ValueError):
        requirement_content('{"artifactType":"requirement_understanding","artifactType":"x"}')
    assert requirement_content('旧文本中引用 "artifactType"="requirement_understanding"')


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", [None, "document_file_id", "document_hash"])
async def test_extraction_retry_cannot_silently_read_replaced_source(monkeypatch, changed_field):
    candidate = run()
    candidate.requirement_id = "requirement-1"
    candidate.snapshot_json.update(documentFileId="file-1", documentHash="hash-1")
    document = SimpleNamespace(document_file_id="file-1", document_hash="hash-1")
    if changed_field:
        setattr(document, changed_field, "replaced")

    async def task(task_id):
        return SimpleNamespace(task_type="requirement_analysis", run_id=candidate.run_id)

    async def get_run(run_id):
        return candidate

    async def get_requirement(requirement_id):
        return document

    service = WorkerTaskService(
        SimpleNamespace(get_ai_run=get_run, get_requirement=get_requirement),
        execution_writer=MemoryExecutionWriter(),
    )
    monkeypatch.setattr(service, "_ai_worker_task", task)
    if changed_field:
        with pytest.raises(AppError, match="原始需求文件已变更"):
            await service.requirement_document("worker-task")
    else:
        assert await service.requirement_document("worker-task") is document


@pytest.mark.parametrize("name", ["document-extraction", "requirement-understanding"])
def test_fully_answered_question_must_be_removed_from_new_output(name):
    value = example(name)
    question = value["questions"][0]
    question["status"] = "resolved"
    question["answer"] = {
        "value": "上游算子为 hoi_tool",
        "confirmationStatus": "confirmed",
        "sourceReferences": [
            {
                "sourceId": value["sources"][0]["id"],
                "locator": "用户明确答复",
                "excerpt": "上游算子为 hoi_tool",
            }
        ],
        "relatedQuestionIds": [],
    }
    value["sources"][0]["type"] = "user_confirmation"
    with pytest.raises(ValueError, match="已解决问题"):
        validate_artifact(value, name.replace("-", "_"))


@pytest.mark.parametrize("name", ["document-extraction", "requirement-understanding"])
def test_answer_can_live_in_business_content_without_question_history(name):
    value = example(name)

    def clear_references(item):
        if isinstance(item, dict):
            if "relatedQuestionIds" in item:
                item["relatedQuestionIds"] = []
            for child in item.values():
                clear_references(child)
        elif isinstance(item, list):
            for child in item:
                clear_references(child)

    clear_references(value)
    value["questions"] = []
    value["sources"].append(
        {
            "id": "CONFIRM",
            "name": "上游算子确认",
            "type": "user_confirmation",
            "location": None,
            "version": None,
        }
    )
    fact = (
        value["extractedFacts"][0]["fact"]
        if name == "document-extraction"
        else value["modules"][0]["operations"][0]["goal"]
    )
    fact.update(
        value="上游算子为 hoi_tool",
        confirmationStatus="confirmed",
        sourceReferences=[
            {"sourceId": "CONFIRM", "locator": "本轮业务答复", "excerpt": "上游算子为 hoi_tool"}
        ],
    )
    if name == "requirement-understanding":
        value["evidence"].append({"id": "ANSWER", **fact.pop("sourceReferences")[0]})
        fact["evidenceIds"] = ["ANSWER"]
    kind = name.replace("-", "_")
    assert validate_artifact(value, kind)["questions"] == []
    fact["relatedQuestionIds"] = ["Q01"]
    with pytest.raises(ValueError, match="relatedQuestionIds"):
        validate_artifact(value, kind)


@pytest.mark.parametrize("name", ["document-extraction", "requirement-understanding"])
def test_partial_answer_preserves_only_the_remaining_open_gap(name):
    value = example(name)
    value["sources"][0]["type"] = "user_confirmation"
    value["questions"][0].update(
        question="已确认上游为 hoi_tool，中间文件字段仍待确认",
        status="open",
        answer={
            "value": "上游算子为 hoi_tool",
            "confirmationStatus": "confirmed",
            "sourceReferences": [
                {
                    "sourceId": value["sources"][0]["id"],
                    "locator": "本轮部分答复",
                    "excerpt": "上游算子为 hoi_tool",
                }
            ],
            "relatedQuestionIds": [],
        },
    )
    if name == "requirement-understanding":
        answer = value["questions"][0]["answer"]
        value["evidence"].append({"id": "ANSWER", **answer.pop("sourceReferences")[0]})
        answer["evidenceIds"] = ["ANSWER"]
    assert validate_artifact(value, name.replace("-", "_"))["questions"][0]["status"] == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["extracting_text", "feature_understanding"])
async def test_revision_accepts_historical_answers_but_save_and_approval_require_clean_output(
    monkeypatch, stage
):
    candidate = run()
    final = stage == "feature_understanding"
    if final:
        candidate.current_stage, candidate.status, candidate.stage_status = (
            "completed",
            "success",
            "completed",
        )
    value = example("requirement-understanding" if final else "document-extraction")
    value["sources"][0]["type"] = "user_confirmation"
    value["questions"][0].update(
        status="resolved",
        answer={
            "value": "上游算子为 hoi_tool",
            "confirmationStatus": "confirmed",
            "sourceReferences": [
                {
                    "sourceId": value["sources"][0]["id"],
                    "locator": "用户答复",
                    "excerpt": "上游算子为 hoi_tool",
                }
            ],
            "relatedQuestionIds": [],
        },
    )
    if final:
        answer = value["questions"][0]["answer"]
        value["evidence"].append({"id": "ANSWER", **answer.pop("sourceReferences")[0]})
        answer["evidenceIds"] = ["ANSWER"]
        candidate.result_yaml = json.dumps(value)
    else:
        candidate.config_json["firstStepOutput"] = value

    async def owned(*args, **kwargs):
        return candidate

    async def nothing(*args):
        pass

    async def latest(*args):
        return SimpleNamespace(llm_connection_id="connection")

    async def connection(*args):
        return SimpleNamespace(connection_id="connection")

    queued = []
    monkeypatch.setattr(workflow, "require_personal_connection", connection)
    monkeypatch.setattr(workflow, "dump_run", lambda row: {"status": row.status})
    service = workflow.GenerationStageWorkflow(
        repository=SimpleNamespace(
            session=None,
            commit=nothing,
            refresh=nothing,
            add=queued.append,
            get_latest_ai_dispatch=latest,
        ),
        owned_run=owned,
        execution_writer=MemoryExecutionWriter(),
    )
    with pytest.raises(AppError, match="已解决问题"):
        await service.save_requirement_analysis_stage_output("run", {"stage": stage}, "user")
    with pytest.raises(AppError, match="已解决问题"):
        await service.review_requirement_analysis_stage(
            "run", {"stage": stage, "action": "approve"}, "user"
        )
    result = await service.revise_requirement_analysis_stage(
        "run",
        {
            "stage": stage,
            "revisionInstruction": "将已回答问题补入正文并删除已解决问题",
            "configJson": deepcopy(candidate.config_json),
        },
        "user",
    )
    assert result["status"] == "pending"
    assert len(queued) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["extracting_text", "feature_understanding", "completed"])
@pytest.mark.parametrize("operation", ["save", "approve", "reject", "revise"])
async def test_rejected_requirement_run_is_read_only(monkeypatch, stage, operation):
    candidate = run()
    candidate.review_status = "rejected"
    candidate.current_stage = stage
    if stage != "extracting_text":
        candidate.status = "success"
        candidate.stage_status = "completed"
    before = deepcopy(vars(candidate))

    async def owned(*args, **kwargs):
        return candidate

    async def nothing(*args):
        pass

    async def latest(*args):
        return SimpleNamespace(llm_connection_id="connection")

    async def connection(*args):
        return SimpleNamespace(connection_id="connection")

    queued = []
    monkeypatch.setattr(workflow, "require_personal_connection", connection)
    monkeypatch.setattr(workflow, "dump_run", lambda value: {"status": value.status})
    service = workflow.GenerationStageWorkflow(
        repository=SimpleNamespace(
            session=None,
            commit=nothing,
            refresh=nothing,
            add=queued.append,
            get_latest_ai_dispatch=latest,
        ),
        owned_run=owned,
        execution_writer=MemoryExecutionWriter(),
    )
    if operation == "save":
        call = service.save_requirement_analysis_stage_output("run", {"stage": stage}, "user")
    elif operation == "revise":
        call = service.revise_requirement_analysis_stage(
            "run",
            {
                "stage": "feature_understanding" if stage == "completed" else stage,
                "revisionInstruction": "重新优化",
            },
            "user",
        )
    else:
        call = service.review_requirement_analysis_stage(
            "run",
            {
                "stage": "feature_understanding" if stage == "completed" else stage,
                "action": operation,
            },
            "user",
        )
    with pytest.raises(AppError):
        await call
    assert vars(candidate) == before
    assert not queued


@pytest.mark.asyncio
async def test_final_rejection_closes_waiting_review_generation(monkeypatch):
    candidate = run()
    candidate.current_stage = "feature_understanding"

    async def owned(*args, **kwargs):
        return candidate

    async def nothing(*args):
        pass

    monkeypatch.setattr(workflow, "dump_run", lambda value: {"reviewStatus": value.review_status})
    service = workflow.GenerationStageWorkflow(
        repository=SimpleNamespace(session=None, commit=nothing, refresh=nothing),
        owned_run=owned,
        execution_writer=MemoryExecutionWriter(),
    )
    result = await service.review_requirement_analysis_stage(
        "run", {"stage": "feature_understanding", "action": "reject"}, "reviewer"
    )
    assert result["reviewStatus"] == "rejected"
    assert candidate.status == "success"
    assert candidate.stage_status == "completed"


def test_compact_result_survives_review_import_and_downstream_snapshot():
    from testing_agent.services.ai_task_output import requirement_source_content

    candidate = run()
    compact = example("requirement-understanding")
    candidate.result_yaml = json.dumps(compact, ensure_ascii=False)
    validate_run_output(candidate, final=True)
    imported = requirement_analysis_import_content(candidate)
    assert json.loads(imported) == compact
    assert (
        json.loads(requirement_source_content(SimpleNamespace(document_content=imported)))
        == compact
    )
    assert json.loads(imported)["schemaVersion"] == "2.0"
    assert "sourceReferences" not in imported
