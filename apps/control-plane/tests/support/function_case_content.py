"""Shared preparation for function case content tests; no collected cases."""

from support.ai_execution import db as db
from support.ui_run_scope import seed
from support.worker_queue_storage import row
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite


def prepare(db):
    seed(db)
    FunctionTestSuite.__table__.create(db.get_bind(), checkfirst=True)
    FunctionTestCase.__table__.create(db.get_bind(), checkfirst=True)
    db.add(row(FunctionTestSuite, suite_id="function-suite", requirement_id="req"))
    db.commit()
