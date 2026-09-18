from copy import deepcopy

import pytest
from test_ui_confirmed_suite_import_flow import UiImportRepository, ui_import_client


def test_ui_import_without_conflicts_completes_without_confirmation():
    repository = UiImportRepository()
    repository.cases = []
    client = ui_import_client(repository)

    response = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["requiresConfirmation"] is False
    assert [case.name for case in repository.cases] == [" login ", "Health"]
    assert repository.run.import_status == "imported"


@pytest.mark.parametrize(
    ("status", "review_status", "import_status"),
    [
        ("failed", "approved", "pending"),
        ("success", "pending", "pending"),
        ("success", "approved", "imported"),
    ],
)
def test_ui_import_rejects_ineligible_runs(status, review_status, import_status):
    repository = UiImportRepository()
    repository.run.status = status
    repository.run.review_status = review_status
    repository.run.import_status = import_status
    client = ui_import_client(repository)

    response = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert response.status_code == 400
    assert repository.commits == 0


def test_ui_import_rejects_suite_owned_by_another_user():
    repository = UiImportRepository()
    repository.project.user_id = "user-2"
    client = ui_import_client(repository)

    response = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert response.status_code == 403
    assert repository.commits == 0


class FailingUiImportRepository(UiImportRepository):
    def __init__(self):
        super().__init__()
        self.fail_next_commit = True
        self.original_case = {
            "name": self.cases[0].name,
            "enabled": self.cases[0].enabled,
            "order_no": self.cases[0].order_no,
            "steps_json": deepcopy(self.cases[0].steps_json),
        }

    async def commit(self):
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("database unavailable")
        await super().commit()

    async def rollback(self):
        await super().rollback()
        existing = self.cases[0]
        existing.name = self.original_case["name"]
        existing.enabled = self.original_case["enabled"]
        existing.order_no = self.original_case["order_no"]
        existing.steps_json = deepcopy(self.original_case["steps_json"])


def test_failed_ui_import_rolls_back_and_remains_retryable_without_changing_review():
    repository = FailingUiImportRepository()
    client = ui_import_client(repository)

    failed = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert failed.status_code == 500
    assert len(repository.cases) == 1
    assert repository.cases[0].name == "Login"
    assert repository.cases[0].steps_json[0]["stepName"] == "Open login"
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "pending"
    assert repository.run.imported_targets == []
    assert repository.run.imported_at is None

    retried = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert retried.status_code == 200
    assert [case.name for case in repository.cases] == [" login ", "Health"]
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "imported"
