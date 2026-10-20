from support.function_candidate_review import (
    FunctionReviewRepository as FunctionReviewRepository,
)
from support.function_candidate_review import (
    make_run as make_run,
)
from support.function_candidate_review import (
    review_client as review_client,
)


def test_function_candidate_can_be_edited_then_approval_freezes_without_importing():
    run = make_run()
    repository = FunctionReviewRepository(run)
    client = review_client(repository)
    candidate = """cases:
  - module: Login
    title: Successful login
    preconditions: Account exists
    steps: Enter credentials
    expectedResults: Home page opens
    priority: P1
    caseType: functional
"""

    saved = client.patch(
        "/v1/function-case-generate-task-runs/run-1/result",
        json={"resultYaml": candidate},
    )
    approved = client.post(
        "/v1/function-case-generate-task-runs/run-1/review",
        json={"action": "approve", "reviewComment": "looks good"},
    )
    frozen = client.patch(
        "/v1/function-case-generate-task-runs/run-1/result",
        json={"resultYaml": "cases: []"},
    )

    assert saved.status_code == 200
    assert saved.json()["data"]["resultYaml"] == candidate
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "approved"
    assert approved.json()["data"]["importStatus"] == "pending"
    assert approved.json()["data"]["importedTargets"] == []
    assert frozen.status_code == 400
    assert run.result_yaml == candidate
    assert repository.commits == 2


def test_only_successful_function_run_can_be_approved():
    run = make_run(status="failed")
    client = review_client(FunctionReviewRepository(run))

    response = client.post(
        "/v1/function-case-generate-task-runs/run-1/review",
        json={"action": "approve"},
    )

    assert response.status_code == 400
    assert run.review_status == "pending"
