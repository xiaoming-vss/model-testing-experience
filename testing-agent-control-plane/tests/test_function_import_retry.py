import pytest
from test_function_confirmed_import import FunctionImportRepository, import_client


class FailsFirstCommitRepository(FunctionImportRepository):
    def __init__(self):
        super().__init__()
        self.commit_attempts = 0
        self.initial_suite_ids = set(self.suites)
        self.initial_case_values = {
            case_id: {
                "module": case.module,
                "title": case.title,
                "content_json": case.content_json,
                "priority": case.priority,
                "case_type": case.case_type,
            }
            for case_id, case in self.cases.items()
        }

    async def commit(self):
        self.commit_attempts += 1
        if self.commit_attempts == 1:
            raise RuntimeError("database unavailable")
        await super().commit()

    async def rollback(self):
        await super().rollback()
        self.suites = {
            suite_id: suite
            for suite_id, suite in self.suites.items()
            if suite_id in self.initial_suite_ids
        }
        self.cases = {
            case_id: case
            for case_id, case in self.cases.items()
            if case_id in self.initial_case_values
        }
        for case_id, values in self.initial_case_values.items():
            case = self.cases[case_id]
            for field, value in values.items():
                setattr(case, field, value)
        self.added.clear()


def test_failed_function_import_preserves_approval_and_can_be_retried():
    repository = FailsFirstCommitRepository()
    client = import_client(repository)

    with pytest.raises(RuntimeError, match="database unavailable"):
        client.post(
            "/v1/function-case-generate-task-runs/run-1/import",
            json={"confirmOverwrite": True},
        )

    assert repository.rollbacks == 1
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "pending"
    assert repository.run.imported_targets == []
    assert repository.run.imported_at is None
    assert set(repository.suites_by_name) == {"Login"}
    assert set(repository.cases) == {"case-existing"}
    assert repository.cases["case-existing"].title == "LOGIN WORKS"

    retried = client.post(
        "/v1/function-case-generate-task-runs/run-1/import",
        json={"confirmOverwrite": True},
    )

    assert retried.status_code == 200
    assert retried.json()["data"]["run"]["reviewStatus"] == "approved"
    assert retried.json()["data"]["run"]["importStatus"] == "imported"
