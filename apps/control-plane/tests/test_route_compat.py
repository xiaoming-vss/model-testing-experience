from testing_agent.app import create_app


def route_set():
    app = create_app()
    result = set()
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            result.add((method.upper(), path))
    return result


def test_test_asset_routes_match_go_contract_subset():
    routes = route_set()

    expected = {
        ("POST", "/v1/requirements/{requirementId}/function-test-suites"),
        ("GET", "/v1/requirements/{requirementId}/function-test-suites"),
        ("GET", "/v1/function-test-suites/{suiteId}"),
        ("PATCH", "/v1/function-test-suites/{suiteId}"),
        ("DELETE", "/v1/function-test-suites/{suiteId}"),
        ("POST", "/v1/function-test-suites/{suiteId}/cases"),
        ("GET", "/v1/function-test-suites/{suiteId}/cases"),
        ("GET", "/v1/function-test-cases/{caseId}"),
        ("PATCH", "/v1/function-test-cases/{caseId}"),
        ("DELETE", "/v1/function-test-cases/{caseId}"),
        ("POST", "/v1/requirements/{requirementId}/api-collections"),
        ("GET", "/v1/requirements/{requirementId}/api-collections"),
        ("GET", "/v1/api-collections/{collectionId}"),
        ("PATCH", "/v1/api-collections/{collectionId}"),
        ("DELETE", "/v1/api-collections/{collectionId}"),
        ("POST", "/v1/api-collections/{collectionId}/cases"),
        ("GET", "/v1/api-collections/{collectionId}/cases"),
        ("GET", "/v1/api-cases/{caseId}"),
        ("PATCH", "/v1/api-cases/{caseId}"),
        ("DELETE", "/v1/api-cases/{caseId}"),
        ("POST", "/v1/projects/{projectId}/api-environments"),
        ("GET", "/v1/projects/{projectId}/api-environments"),
        ("POST", "/v1/requirements/{requirementId}/ui-test-suites"),
        ("GET", "/v1/requirements/{requirementId}/ui-test-suites"),
        ("POST", "/v1/ui-test-suites/{suiteId}/cases"),
        ("GET", "/v1/ui-test-suites/{suiteId}/cases"),
    }

    assert expected <= routes


def test_openapi_paths_use_go_camel_case_path_parameters():
    app = create_app()
    paths = set(app.openapi()["paths"])

    assert "/v1/projects/{projectId}" in paths
    assert "/internal/api-worker/tasks/{taskId}/collection-items/{itemId}/completed" in paths
    assert "/v1/projects/{project_id}" not in paths
    assert "/v1/projects/{projectId}/skills/default-sync" not in paths
