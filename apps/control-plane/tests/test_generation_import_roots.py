"""Import roots are resolved from bound, server-owned business inputs."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_import_seed import seed_api_or_ui_import_graph, seed_import_graph

from testing_agent.domain.api_interface import path_key
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_document_preparation import (
    PreparedFile,
    PreparedRequirementDocument,
)
from testing_agent.services.generation_import_roots import lock_import_roots


async def test_function_import_uses_locked_prepared_document(database):  # noqa: F811
    sync, _, _ = database
    seed_import_graph(sync)
    content = b"document"
    digest = sha256(content).hexdigest()
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type, requirement.document_file_id = "docx", "document"
    requirement.document_filename, requirement.document_hash = "document.docx", digest
    sync.add(
        StoredFile(
            file_id="document",
            project_id="p",
            uploaded_by="u",
            filename="document.docx",
            content_type="application/octet-stream",
            size=len(content),
            sha256=digest,
            bucket="bucket",
            object_key="object",
            staging_key="",
            status="attached",
            purpose="requirement",
            resource_type="requirement",
            resource_id="req",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    sync.commit()
    prepared = PreparedRequirementDocument(
        "req",
        "docx",
        PreparedFile(
            "document",
            "p",
            "requirement",
            "document.docx",
            "application/octet-stream",
            "bucket",
            "object",
            len(content),
            digest,
        ),
        (),
    )
    options = dict(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        expected_current_token="current-d",
    )
    roots = await lock_import_roots(
        AsyncSessionAdapter(sync), prepared_document=prepared, **options
    )
    assert ("requirement_document", "req") in roots
    sync.rollback()
    sync.query(StoredFile).filter_by(file_id="document").one().object_key = "changed"
    sync.commit()
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await lock_import_roots(AsyncSessionAdapter(sync), prepared_document=prepared, **options)


async def test_api_import_uses_only_bound_task_interfaces(database):  # noqa: F811
    sync, _, _ = database
    seed_api_or_ui_import_graph(sync, "api", "cases: []")
    sync.add(
        SoftwareRepository(
            software_repository_id="repository",
            project_id="p",
            name="API",
            base_path="/v1",
            repository_instance_url="https://git.example",
            repository_path="group/repo",
            created_by_user_id="u",
        )
    )
    sync.flush()
    sync.add(
        ApiInterface(
            interface_id="interface",
            software_repository_id="repository",
            name="API",
            method="GET",
            path="/x",
            path_key=path_key("/x"),
        )
    )
    task = sync.query(AiGenerateTask).filter_by(task_id="api-task").one()
    task.interface_ids_json = ["interface"]
    sync.commit()
    options = dict(
        requirement_id="req", kind="api", stage="generate", expected_current_token="api-current-2"
    )
    first = await lock_import_roots(AsyncSessionAdapter(sync), **options)
    sync.query(ApiInterface).filter_by(interface_id="interface").one().description = "changed"
    sync.flush()
    second = await lock_import_roots(AsyncSessionAdapter(sync), **options)
    assert first != second
    task.interface_ids_json = ["missing"]
    sync.flush()
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await lock_import_roots(AsyncSessionAdapter(sync), **options)


async def test_ui_import_reads_selected_cases_and_pin_from_current_storage(database):  # noqa: F811
    sync, _, _ = database
    seed_api_or_ui_import_graph(sync, "ui", "[]")
    sync.add(FunctionTestSuite(suite_id="suite", requirement_id="req", name="module"))
    sync.flush()
    sync.add(FunctionTestCase(case_id="functional-case", suite_id="suite", title="selected"))
    sync.add(FunctionTestCase(case_id="other", suite_id="suite", title="unselected"))
    sync.commit()
    options = dict(
        requirement_id="req", kind="ui", stage="ui_yaml", expected_current_token="ui-current-2"
    )
    first = await lock_import_roots(AsyncSessionAdapter(sync), **options)
    sync.query(FunctionTestCase).filter_by(case_id="other").one().title = "changed other"
    sync.flush()
    assert await lock_import_roots(AsyncSessionAdapter(sync), **options) == first
    sync.query(FunctionTestCase).filter_by(
        case_id="functional-case"
    ).one().title = "changed selected"
    sync.flush()
    assert await lock_import_roots(AsyncSessionAdapter(sync), **options) != first
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_import_roots(
            AsyncSessionAdapter(sync), **{**options, "expected_current_token": "old"}
        )
