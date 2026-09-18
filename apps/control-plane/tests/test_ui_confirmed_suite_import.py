from testing_agent.app import create_app


def test_ui_confirmed_suite_import_route_is_public():
    paths = create_app().openapi()["paths"]

    assert "post" in paths["/v1/ui-case-generate-task-runs/{runId}/import"]
