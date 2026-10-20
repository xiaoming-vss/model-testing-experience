from support.ui_confirmed_suite_import_flow import (
    UiImportRepository as UiImportRepository,
)
from support.ui_confirmed_suite_import_flow import (
    approved_ui_run as approved_ui_run,
)
from support.ui_confirmed_suite_import_flow import (
    ui_import_client as ui_import_client,
)


def test_ui_import_previews_full_conflict_then_confirms_in_place_and_only_once():
    repository = UiImportRepository()
    client = ui_import_client(repository)

    preview = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1"},
    )

    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["requiresConfirmation"] is True
    assert data["conflicts"] == [
        {
            "normalizedName": "login",
            "existingCase": {
                "name": "Login",
                "enabled": True,
                "orderNo": 1,
                "stepsJson": repository.cases[0].steps_json,
            },
            "generatedCase": {
                "name": " login ",
                "enabled": False,
                "orderNo": 7,
                "stepsJson": [
                    {
                        "orderNo": 1,
                        "stepName": "Enter username",
                        "keyword": "fill",
                        "locatorType": "test_id",
                        "locatorValue": "username",
                        "operationValue": "alice",
                        "continueOnFailure": True,
                        "enabled": False,
                    }
                ],
            },
        }
    ]
    assert len(repository.cases) == 1
    assert repository.commits == 0
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "pending"

    confirmed = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )
    formal_cases = client.get("/v1/ui-test-suites/suite-1/cases")
    run_status = client.get("/v1/ui-case-generate-task-runs/run-1")
    repeated = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["requiresConfirmation"] is False
    assert formal_cases.status_code == 200
    imported = formal_cases.json()["data"]["items"]
    assert [case["caseId"] for case in imported] == ["case-existing", imported[1]["caseId"]]
    assert imported[0]["name"] == " login "
    assert imported[0]["enabled"] is False
    assert imported[0]["orderNo"] == 7
    assert imported[0]["stepsJson"][0]["locatorValue"] == "username"
    assert imported[1]["name"] == "Health"
    assert run_status.status_code == 200
    assert run_status.json()["data"]["reviewStatus"] == "approved"
    assert run_status.json()["data"]["importStatus"] == "imported"
    assert run_status.json()["data"]["importedTargets"] == [
        {"targetType": "ui_suite", "targetId": "suite-1"}
    ]
    assert run_status.json()["data"]["importedAt"] is not None
    assert repeated.status_code == 400
