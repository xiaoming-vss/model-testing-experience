from test_function_confirmed_import import FunctionImportRepository, import_client


def test_function_import_without_conflicts_creates_all_suites_in_one_request():
    repository = FunctionImportRepository()
    repository.run.result_yaml = """cases:
  - module: Profile
    title: Update display name
  - module: Search
    title: Find an order
"""
    client = import_client(repository)

    response = client.post("/v1/function-case-generate-task-runs/run-1/import", json={})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requiresConfirmation"] is False
    assert data["conflicts"] == []
    assert data["run"]["importStatus"] == "imported"
    assert [target["targetId"] for target in data["run"]["importedTargets"]] == [
        repository.suites_by_name["Profile"].suite_id,
        repository.suites_by_name["Search"].suite_id,
    ]
    assert {case.title for case in repository.cases.values()} == {
        "LOGIN WORKS",
        "Update display name",
        "Find an order",
    }
    assert repository.commits == 1
