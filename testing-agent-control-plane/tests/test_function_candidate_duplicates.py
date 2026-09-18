from test_function_candidate_review import FunctionReviewRepository, make_run, review_client


def test_function_approval_rejects_duplicate_candidate_names_within_a_module():
    run = make_run()
    run.result_yaml = """cases:
  - module: Login
    title: Login works
  - module: Login
    title: " login WORKS "
"""
    client = review_client(FunctionReviewRepository(run))

    response = client.post(
        "/v1/function-case-generate-task-runs/run-1/review",
        json={"action": "approve"},
    )

    assert response.status_code == 400
    assert run.review_status == "pending"
