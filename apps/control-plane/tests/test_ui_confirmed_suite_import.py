from support.openapi_schema import openapi_schema


def test_ui_confirmed_suite_import_route_is_public():
    paths = openapi_schema()["paths"]

    assert "post" in paths["/v1/ui-case-generate-task-runs/{runId}/import"]
