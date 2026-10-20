from support.function_confirmed_import import (
    FunctionImportRepository as FunctionImportRepository,
)
from support.function_confirmed_import import (
    approved_run as approved_run,
)
from support.function_confirmed_import import (
    import_client as import_client,
)


def test_function_import_previews_conflicts_then_overwrites_across_all_suites():
    repository = FunctionImportRepository()
    client = import_client(repository)

    preview = client.post("/v1/function-case-generate-task-runs/run-1/import", json={})

    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["requiresConfirmation"] is True
    assert preview_data["conflicts"] == [
        {
            "normalizedName": "login works",
            "existingCase": {
                "module": "Login",
                "title": "LOGIN WORKS",
                "preconditions": "Old account exists",
                "steps": "Enter old credentials",
                "expectedResults": "Old home page opens",
                "priority": "P2",
                "caseType": "smoke",
            },
            "generatedCase": {
                "module": "Login",
                "title": "login works",
                "preconditions": "New account exists",
                "steps": "Enter new credentials",
                "expectedResults": "New home page opens",
                "priority": "P0",
                "caseType": "regression",
            },
        }
    ]
    assert repository.added == []
    assert repository.commits == 0
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "pending"

    confirmed = client.post(
        "/v1/function-case-generate-task-runs/run-1/import",
        json={"confirmOverwrite": True},
    )

    assert confirmed.status_code == 200
    confirmed_data = confirmed.json()["data"]
    assert confirmed_data["requiresConfirmation"] is False
    assert confirmed_data["run"]["reviewStatus"] == "approved"
    assert confirmed_data["run"]["importStatus"] == "imported"
    assert "importedCollectionId" not in confirmed_data["run"]
    assert confirmed_data["run"]["importedTargets"] == [
        {"targetType": "function_suite", "targetId": "suite-login"},
        {
            "targetType": "function_suite",
            "targetId": repository.suites_by_name["Checkout"].suite_id,
        },
    ]
    assert repository.cases["case-existing"].title == "login works"
    assert repository.cases["case-existing"].preconditions == "New account exists"
    # 覆盖写入的用例保持原 ID；新用例沿用候选编号。
    assert repository.cases["case-existing"].case_id == "case-existing"
    assert repository.cases["candidate-submit"].title == "Submit order"
    assert any(case.title == "Submit order" for case in repository.cases.values())
    assert repository.commits == 1

    repeated = client.post(
        "/v1/function-case-generate-task-runs/run-1/import",
        json={"confirmOverwrite": True},
    )
    assert repeated.status_code == 400


def test_function_import_enforces_requirement_ownership():
    repository = FunctionImportRepository(owner="user-2")
    client = import_client(repository)

    response = client.post("/v1/function-case-generate-task-runs/run-1/import", json={})

    assert response.status_code == 403
    assert repository.added == []
