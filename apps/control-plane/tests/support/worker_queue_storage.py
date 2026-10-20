"""Shared preparation for worker queue storage tests; no collected cases."""

from sqlalchemy import Boolean, Integer

from support.ai_execution import db as db
from support.mysql_initialization import mysql as mysql
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun


def row(model, **values):
    for col in model.__table__.columns:
        if col.name in values or col.nullable or col.default is not None or col.primary_key:
            continue
        values[col.name] = (
            False
            if isinstance(col.type, Boolean)
            else (0 if isinstance(col.type, Integer) else "test")
        )
    return model(**values)


def add_business_tables(db):
    from support.api_run_scope import seed
    from testing_agent.models.api_case import ApiCase

    seed(db)
    db.add(row(ApiCase, case_id="case", collection_id="collection"))
    db.flush()

    for model in (
        ApiCaseRun,
        ApiCollectionRun,
        ApiCollectionRunItem,
        UiTestCaseRun,
        UiTestSuiteRun,
    ):
        model.__table__.create(db.get_bind(), checkfirst=True)
