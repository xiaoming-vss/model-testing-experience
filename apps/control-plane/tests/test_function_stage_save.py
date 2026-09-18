from copy import deepcopy

import pytest
from test_function_candidate_review import FunctionReviewRepository, make_run, review_client


def editable_run():
    run = make_run(status="waiting_review")
    run.checkpoint_enabled = True
    run.current_stage = "requirement_analysis"
    run.stage_status = "waiting_review"
    run.config_json = {"enhancedText": "source", "requirementAnalysis": {"purpose": "old"}}
    return run


@pytest.mark.parametrize(
    "overrides",
    [
        {"checkpoint_enabled": False},
        *({"status": status} for status in ["pending", "running", "success", "failed", "canceled"]),
        {"review_status": "approved"},
        {"review_status": "rejected"},
        {"import_status": "imported"},
        {"stage_status": "running"},
        {"current_stage": "detailed_cases"},
    ],
)
def test_stage_save_rejects_noneditable_run_without_mutation(overrides):
    run = editable_run()
    run.__dict__.update(overrides)
    assert_rejected(run, {"stage": run.current_stage, "configJson": {"purpose": "new"}})


def assert_rejected(run, payload):
    before = deepcopy(vars(run))
    repo = FunctionReviewRepository(run)
    client = review_client(repo)
    response = client.patch("/v1/function-case-generate-task-runs/run-1/stage-output", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == 400
    assert {key: value for key, value in vars(run).items() if not key.startswith("_")} == before
    assert repo.commits == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"stage": "case_names"},
        {"currentStage": "case_names"},
        {"resultYaml": "unreviewed replacement"},
        {"resultSummaryJson": {"changed": True}},
        {"stageStatus": "completed"},
        {
            "configJson": {
                "requirementAnalysis": {"purpose": "new"},
                "caseNames": {"categories": []},
            }
        },
        {"configJson": {"caseNames": {"categories": []}}},
        {"configJson": {"enhancedText": "replace upstream"}},
        {"configJson": "bad json"},
        {"configJson": []},
    ],
)
def test_stage_save_rejects_out_of_scope_fields_without_mutation(patch):
    assert_rejected(
        editable_run(), {"stage": "requirement_analysis", "configJson": {"purpose": "new"}, **patch}
    )
