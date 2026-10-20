import pytest
from sqlalchemy import select
from support.ai_execution import create_run
from support.ai_execution import db as db

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.worker_context import AiWorkerContext, ApiWorkerContext, UiWorkerContext
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_context import read_worker_context


def test_ai_context_reads_frozen_connection_without_mutating_queue(db):
    _, task = create_run(db)
    task_id = task.task_id
    db.expunge_all()
    loaded = db.scalar(select(WorkerTask).where(WorkerTask.task_id == task_id))
    before = dict(loaded.__dict__)
    assert read_worker_context(db, loaded) == AiWorkerContext("task", "llm")
    assert loaded.__dict__ == before
    assert not db.dirty


@pytest.mark.parametrize(
    "domain,task_type,run_id,expected",
    [
        ("api", "api_collection_run", "ac-run", ApiWorkerContext(None, "ac", "ac-run")),
        ("api", "api_case_run", "api-run", ApiWorkerContext("api", "ac", "ac-run")),
        ("ui", "suite_run", "us-run", UiWorkerContext(None, "us")),
        ("ui", "case_run", "ui-run", UiWorkerContext("ui", "us")),
    ],
)
def test_context_resolves_domain_owner_without_adding_queue_fields(
    db, domain, task_type, run_id, expected
):
    create_run(db)
    db.add_all(
        [
            ApiCollection(collection_id="ac", requirement_id="r", name="API"),
            UiTestSuite(suite_id="us", requirement_id="r", name="UI"),
        ]
    )
    db.flush()
    db.add_all(
        [
            ApiCase(
                case_id="api", collection_id="ac", name="API case", method="GET", url_template="/"
            ),
            UiTestCase(case_id="ui", suite_id="us", name="UI case", steps_json=[]),
        ]
    )
    db.flush()
    db.add_all(
        [
            ApiCollectionRun(
                collection_run_id="ac-run",
                collection_id="ac",
                environment_id="",
                trigger_user_id="u",
            ),
            ApiCaseRun(
                run_id="api-run",
                case_id="api",
                collection_id="ac",
                collection_run_id="ac-run",
                environment_id="",
                trigger_user_id="u",
            ),
            UiTestSuiteRun(suite_run_id="us-run", suite_id="us", trigger_user_id="u"),
            UiTestCaseRun(run_id="ui-run", case_id="ui", suite_id="us", trigger_user_id="u"),
        ]
    )
    task = WorkerTask(domain=domain, task_type=task_type, task_id="dispatch", run_id=run_id)
    db.add(task)
    db.commit()
    before = dict(task.__dict__)
    assert read_worker_context(db, task) == expected
    assert task.__dict__ == before
    assert not db.dirty


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("ai", AiWorkerContext(None, None)),
        ("api", ApiWorkerContext(None, None, None)),
        ("ui", UiWorkerContext(None, None)),
    ],
)
def test_missing_execution_has_no_invented_identity(db, domain, expected):
    task = WorkerTask(domain=domain, task_type="case_run", task_id="absent", run_id="absent")
    assert read_worker_context(db, task) == expected


def test_unknown_domain_is_not_treated_as_ui(db):
    task = WorkerTask(domain="unknown", task_type="case_run", task_id="x", run_id="x")
    with pytest.raises(type(ErrBadRequest)):
        read_worker_context(db, task)


def test_claim_payload_uses_context_instead_of_stale_queue_attributes():
    from testing_agent.services.worker_domains.events import task_payload

    task = WorkerTask(
        domain="ui", task_type="case_debug", task_id="dispatch", run_id="run", status="claimed"
    )
    task.suite_id = "stale-suite"
    task.case_id = "stale-case"
    payload = task_payload(task, UiWorkerContext("case", "suite"))
    assert payload["caseId"] == "case"
    assert payload["suiteId"] == "suite"
    assert payload["collectionId"] is None
    assert payload["generateTaskId"] is None
    assert payload["status"] == "claimed"


@pytest.mark.parametrize("domain", ["api", "ui"])
async def test_snapshot_rejects_context_for_another_domain(domain):
    from testing_agent.services.worker import build_snapshot

    task = WorkerTask(domain=domain, task_type="case_debug", task_id="x", run_id="x")
    with pytest.raises(type(ErrBadRequest)):
        await build_snapshot(None, domain, task, context=AiWorkerContext("task", "llm"))
