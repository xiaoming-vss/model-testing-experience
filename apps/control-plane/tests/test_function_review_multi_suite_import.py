from support.openapi_schema import openapi_schema


def test_function_candidate_edit_and_confirmed_import_routes_are_public():
    paths = openapi_schema()["paths"]

    assert "patch" in paths["/v1/function-case-generate-task-runs/{runId}/result"]
    assert "post" in paths["/v1/function-case-generate-task-runs/{runId}/import"]
