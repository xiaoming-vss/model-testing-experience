"""Shared preparation for api run scope tests; no collected cases."""

from sqlalchemy import select

from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db
from support.ui_run_scope import seed as seed_ui
from support.worker_queue_storage import row
from testing_agent.db.base import Base
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService


def seed(db):
    seed_ui(db)
    models = (
        ApiCase,
        ApiCollection,
        ApiCaseRun,
        ApiCollectionRun,
        ApiCollectionRunItem,
        ApiEnvironment,
        ApiEnvironmentVar,
    )
    Base.metadata.create_all(db.get_bind(), tables=[m.__table__ for m in models])
    for item in [
        row(ApiCollection, collection_id="collection", requirement_id="req"),
        row(
            ApiCase,
            case_id="api-case",
            collection_id="collection",
            method="GET",
            url_template="/ping",
        ),
        row(
            ApiEnvironment,
            environment_id="env",
            project_id="p1",
            base_url="https://example.test",
        ),
    ]:
        db.add(item)
        db.flush()
    history = db.scalar(select(SprintDailyMetrics))
    history.api_case_total = 11
    history.api_case_success = 9
    db.commit()


def services(db):
    adapter = AsyncSessionAdapter(db)
    return (
        ApiCaseService(ApiCaseRepository(adapter)),
        ApiCollectionRunService(ApiCollectionRunRepository(adapter)),
    )
