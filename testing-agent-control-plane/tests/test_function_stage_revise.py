import asyncio
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from test_function_candidate_review import FunctionReviewRepository, make_run, review_client

from testing_agent.core.errors import ErrBadRequest, ErrForbidden
from testing_agent.services.ai_generate_task import AiGenerateTaskService


class RevisionRepository(FunctionReviewRepository):
    session = AuthorizationDatabase()

    def __init__(self, run):
        super().__init__(run)
        self.queued = []
        self.lock = asyncio.Lock()
        self.latest = SimpleNamespace(llm_connection_id="llm-1")

    async def get_run_for_update(self, run_id):
        await self.lock.acquire()
        return self.run

    async def get_latest_worker_task_by_run_id(self, run_id):
        return self.latest

    def add(self, task):
        self.queued.append(task)

    async def commit(self):
        await super().commit()
        if self.lock.locked():
            self.lock.release()

    async def get_project(self, project_id):
        return SimpleNamespace(user_id="user-1", project_id="project-1")


def revision_run(stage="requirement_analysis"):
    run = make_run(status="waiting_review")
    run.checkpoint_enabled = True
    run.current_stage = stage
    run.stage_status = "waiting_review"
    run.config_json = {"requirementAnalysis": {"old": True}, "caseNames": {"categories": []}}
    if stage == "detailed_cases":
        run.status = "success"
        run.result_yaml = '{"cases":[{"name":"existing", "module":"login"}]}'
    return run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,field", [("requirement_analysis", "requirementAnalysis"), ("case_names", "caseNames")]
)
async def test_revision_saves_edits_and_queues_current_stage(stage, field):
    run = revision_run(stage)
    repo = RevisionRepository(run)
    result = await AiGenerateTaskService(repo).revise_function_case_stage(
        "run-1",
        {
            "stage": stage,
            "revisionInstruction": " cover boundaries ",
            "configJson": {field: {"edited": True}, "enhancedText": "must not overwrite"},
        },
        "user-1",
    )
    assert result["currentStage"] == stage
    assert result["status"] == "pending"
    assert run.config_json[field] == {"edited": True}
    assert "enhancedText" not in run.config_json
    assert run.config_json["revisionInstruction"] == "cover boundaries"
    assert repo.commits == 1
    assert repo.queued[0].run_id == "run-1"
    assert repo.queued[0].llm_connection_id == "llm-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint", [False, True])
async def test_final_revision_accepts_unsaved_result_without_restarting_chain(checkpoint):
    run = revision_run("detailed_cases")
    run.current_stage = "completed"
    run.checkpoint_enabled = checkpoint
    repo = RevisionRepository(run)
    edited = '{"cases":[{"name":"edited", "module":"login"}]}'
    await AiGenerateTaskService(repo).revise_function_case_stage(
        "run-1",
        {
            "stage": "detailed_cases",
            "revisionInstruction": "cover errors",
            "resultYaml": edited,
        },
        "user-1",
    )
    assert run.current_stage == "detailed_cases"
    assert run.result_yaml == edited
    assert "edited" in run.config_json["resultYaml"]
    assert run.review_status == "pending"
    assert run.checkpoint_enabled is checkpoint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,body",
    [
        ({"status": "running"}, {}),
        ({"review_status": "approved"}, {}),
        ({"review_status": "rejected"}, {}),
        ({"import_status": "imported"}, {}),
        ({}, {"stage": "case_names"}),
        ({}, {"revisionInstruction": "  "}),
        ({}, {"configJson": {"requirementAnalysis": " "}}),
        ({"checkpoint_enabled": False}, {}),
    ],
)
async def test_invalid_revision_never_queues(changes, body):
    run = revision_run()
    for key, value in changes.items():
        setattr(run, key, value)
    repo = RevisionRepository(run)
    with pytest.raises(type(ErrBadRequest)):
        await AiGenerateTaskService(repo).revise_function_case_stage(
            "run-1",
            {
                "stage": "requirement_analysis",
                "revisionInstruction": "improve",
                **body,
            },
            "user-1",
        )
    assert not repo.queued
    assert repo.commits == 0


@pytest.mark.asyncio
async def test_concurrent_revision_queues_once():
    repo = RevisionRepository(revision_run())

    async def revise():
        return await AiGenerateTaskService(repo).revise_function_case_stage(
            "run-1",
            {
                "stage": "requirement_analysis",
                "revisionInstruction": "improve",
            },
            "user-1",
        )

    results = await asyncio.gather(revise(), revise(), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(repo.queued) == 1


@pytest.mark.asyncio
async def test_revision_checks_ownership_before_lock():
    repo = RevisionRepository(revision_run())
    with pytest.raises(type(ErrForbidden)):
        await AiGenerateTaskService(repo).revise_function_case_stage("run-1", {}, "other-user")
    assert not repo.lock.locked()
    assert not repo.queued


def test_revision_http_contract():
    repo = RevisionRepository(revision_run())
    response = review_client(repo).post(
        "/v1/function-case-generate-task-runs/run-1/stage-revise",
        json={
            "stage": "requirement_analysis",
            "revisionInstruction": "improve",
            "configJson": {"requirementAnalysis": {"edited": True}},
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result", ["", "not valid json", '{"cases":[]}', '{"cases":[{"steps":"missing title"}]}']
)
async def test_final_revision_rejects_invalid_candidate(result):
    repo = RevisionRepository(revision_run("detailed_cases"))
    with pytest.raises(type(ErrBadRequest)):
        await AiGenerateTaskService(repo).revise_function_case_stage(
            "run-1",
            {
                "stage": "detailed_cases",
                "revisionInstruction": "improve",
                "resultYaml": result,
            },
            "user-1",
        )
    assert repo.commits == 0
    assert not repo.queued


@pytest.mark.asyncio
async def test_revision_without_previous_worker_does_not_save_edits():
    run = revision_run()
    repo = RevisionRepository(run)
    repo.latest = None
    with pytest.raises(type(ErrBadRequest)):
        await AiGenerateTaskService(repo).revise_function_case_stage(
            "run-1",
            {
                "stage": "requirement_analysis",
                "revisionInstruction": "improve",
                "configJson": {"requirementAnalysis": {"changed": True}},
            },
            "user-1",
        )
    assert run.config_json["requirementAnalysis"] == {"old": True}
    assert run.status == "waiting_review"
    assert repo.commits == 0
