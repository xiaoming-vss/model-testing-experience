from testing_agent.app import create_app


def openapi_route_set():
    result = set()
    for path, methods in create_app().openapi()["paths"].items():
        for method in methods:
            result.add((method.upper(), path))
    return result


def test_run_routes_match_go_contract_subset():
    routes = openapi_route_set()

    expected = {
        ("POST", "/v1/api-cases/{caseId}/run"),
        ("GET", "/v1/api-case-runs/{runId}"),
        ("POST", "/v1/api-collections/{collectionId}/run"),
        ("GET", "/v1/api-collections/{collectionId}/runs"),
        ("GET", "/v1/api-collection-runs/{collectionRunId}"),
        ("GET", "/v1/api-collection-runs/{collectionRunId}/report"),
        ("POST", "/v1/ui-test-cases/{caseId}/debug-run"),
        ("GET", "/v1/ui-test-case-runs/{runId}"),
        ("POST", "/v1/ui-test-suites/{suiteId}/run"),
        ("GET", "/v1/ui-test-suites/{suiteId}/runs"),
        ("GET", "/v1/ui-test-suite-runs/{suiteRunId}"),
        ("GET", "/v1/ui-test-suite-runs/{suiteRunId}/report"),
    }

    assert expected <= routes
