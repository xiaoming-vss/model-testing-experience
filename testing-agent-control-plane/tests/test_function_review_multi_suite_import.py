from testing_agent.app import create_app


def test_function_candidate_edit_and_confirmed_import_routes_are_public():
    paths = create_app().openapi()["paths"]

    assert "patch" in paths["/v1/function-case-generate-task-runs/{runId}/result"]
    assert "post" in paths["/v1/function-case-generate-task-runs/{runId}/import"]
