"""MySQL REPEATABLE READ importers use locked current rows after an old snapshot."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.generation import generation_services
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.domain.function_case_identity import pinned_case_id
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.models import Base
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_import_receipts import (
    record_current_import,
    reserve_import_request,
)
from testing_agent.repositories.generation_import_targets import lock_import_target_state


def test_old_transaction_snapshot_cannot_hide_new_conflicts_or_cases(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            connection,
            tables["requirements"],
            {"requirement_id": "req", "sprint_id": sprint["sprint_id"]},
        )
        seed_row(
            connection,
            tables["api_collections"],
            {"collection_id": "api", "requirement_id": "req", "name": "api"},
        )
        seed_row(
            connection,
            tables["function_test_suites"],
            {"suite_id": "suite", "requirement_id": "req", "name": "module"},
        )
        seed_row(
            connection,
            tables["function_test_cases"],
            {"case_id": "original", "suite_id": "suite", "title": "old"},
        )
    payload = """cases:
  - name: fresh-conflict
    method: GET
    urlTemplate: /fresh
    bodyType: none
"""

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as reader, factory() as writer:
                await reader.scalar(sa.select(sa.func.count()).select_from(ApiCase))
                await reader.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase))
                writer.add(
                    ApiCase(
                        case_id="fresh-api",
                        collection_id="api",
                        name="fresh-conflict",
                        method="GET",
                        url_template="/fresh",
                    )
                )
                writer.add(
                    FunctionTestCase(
                        case_id="global-id", suite_id="suite", title="new", order_no=99
                    )
                )
                await writer.flush()
                writer.add(
                    ApiAssertRule(
                        assert_rule_id="fresh-rule",
                        case_id="fresh-api",
                        name="status",
                        assert_source="status_code",
                        target_expr="",
                        comparator="eq",
                        expected_value="200",
                    )
                )
                await writer.commit()
                await lock_import_target_state(
                    reader, requirement_id="req", kind="api", target_id="api"
                )
                repository = AiGenerateTaskRepository(reader)
                bundle = generation_services(repository)
                source = SimpleNamespace(
                    result_yaml=payload, snapshot_json={}, requirement_id="req", run_id="audit"
                )
                result = await bundle.api_importer.import_api_run(
                    "audit",
                    "api",
                    False,
                    project["user_id"],
                    artifact_content=payload,
                    approved_source=source,
                    preview_only=True,
                    locking_reads=True,
                )
                assert result["requiresConfirmation"] and len(result["conflicts"]) == 1
                assert result["conflicts"][0]["existingCase"]["assertRules"][0]["name"] == "status"
                await lock_import_target_state(
                    reader, requirement_id="req", kind="function", target_id=""
                )
                assert await pinned_case_id(repository, "global-id", for_update=True) != "global-id"
                reservation, replayed = await reserve_import_request(
                    reader,
                    request_id=str(uuid4()),
                    fingerprint="fingerprint",
                    requirement_id="req",
                    actor_id=project["user_id"],
                )
                assert not replayed
                source_info = CurrentImportSource(
                    requirement_id="req",
                    chain_id="chain",
                    kind="function",
                    stage="detailed_cases",
                    stage_id="stage",
                    task_id="task",
                    candidate_id="candidate",
                    snapshot_id="snapshot",
                    source_attempt_id=None,
                    content_token="token",
                    content="output",
                    format="text",
                    context=None,
                    source_manifest={},
                    source_snapshot={"source": {}, "config": {}},
                    upstream_outputs=(),
                    content_hash="hash",
                    basis_hash="basis",
                    source_lineage_hash="source-lineage",
                    full_lineage_hash="full-lineage",
                    confirmed_by=None,
                    confirmed_at=None,
                    review_comment=None,
                )
                recorded = await record_current_import(
                    reader,
                    request=reservation,
                    source=source_info,
                    target_id="",
                    actor_id=project["user_id"],
                    changes=[
                        {
                            "targetType": "function_suite",
                            "targetId": "suite",
                            "changedCaseIds": ["original"],
                        }
                    ],
                )
                assert recorded["importRecords"][0]["targetCaseCount"] == 2
                await reader.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
