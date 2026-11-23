"""Current document roots are checked against locked, scoped file metadata."""

from datetime import UTC, datetime, timedelta

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401

from testing_agent.domain.api_interface import path_key
from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_root_input,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_root_inputs import (
    lock_api_interface_root,
    lock_requirement_document_root,
    lock_ui_repository_cases_root,
    lock_ui_repository_cases_source,
)
from testing_agent.services.ai_task_output import build_generate_run_snapshot


def seed_file(sync, file_id, *, purpose, filename, digest, requirement="req"):
    sync.add(
        StoredFile(
            file_id=file_id,
            project_id="p",
            uploaded_by="u",
            filename=filename,
            content_type="text/html" if purpose == "requirement" else "image/png",
            size=10,
            sha256=digest,
            bucket="bucket",
            object_key=file_id,
            staging_key="",
            status="attached",
            purpose=purpose,
            resource_type="requirement",
            resource_id=requirement,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )


async def test_document_root_includes_referenced_images_but_not_unrelated_files(database):  # noqa: F811
    sync, _, _ = database
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type = "richtext"
    requirement.document_file_id = "document"
    requirement.document_filename = "requirements.html"
    requirement.document_hash = "doc-hash"
    seed_file(
        sync, "document", purpose="requirement", filename="requirements.html", digest="doc-hash"
    )
    seed_file(sync, "image", purpose="attachment", filename="image.png", digest="image-hash")
    seed_file(sync, "unrelated", purpose="attachment", filename="other.png", digest="other-hash")
    sync.commit()
    session = AsyncSessionAdapter(sync)
    with pytest.raises(IncompleteRootInput, match="unknown"):
        await lock_requirement_document_root(
            session, requirement_id="req", referenced_attachment_ids=None
        )
    first = await lock_requirement_document_root(
        session, requirement_id="req", referenced_attachment_ids=("image",)
    )
    unrelated = sync.query(StoredFile).filter_by(file_id="unrelated").one()
    unrelated.sha256 = "different-other-hash"
    sync.flush()
    same = await lock_requirement_document_root(
        session, requirement_id="req", referenced_attachment_ids=("image",)
    )
    assert same == first
    image = sync.query(StoredFile).filter_by(file_id="image").one()
    image.sha256 = "different-image-hash"
    sync.flush()
    changed = await lock_requirement_document_root(
        session, requirement_id="req", referenced_attachment_ids=("image",)
    )
    assert changed.content_hash != first.content_hash


async def test_missing_or_mismatched_file_metadata_cannot_become_valid(database):  # noqa: F811
    sync, _, _ = database
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type = "docx"
    requirement.document_file_id = "document"
    requirement.document_filename = "requirements.docx"
    requirement.document_hash = "expected"
    seed_file(sync, "document", purpose="requirement", filename="requirements.docx", digest="other")
    sync.commit()
    session = AsyncSessionAdapter(sync)
    with pytest.raises(IncompleteRootInput, match="inconsistent"):
        await lock_requirement_document_root(
            session, requirement_id="req", referenced_attachment_ids=None
        )
    document = sync.query(StoredFile).filter_by(file_id="document").one()
    document.sha256 = "expected"
    document.status = "deleting"
    sync.flush()
    with pytest.raises(IncompleteRootInput, match="unavailable"):
        await lock_requirement_document_root(
            session, requirement_id="req", referenced_attachment_ids=None
        )


async def test_api_root_matches_actual_worker_snapshot_and_ignores_unselected_interfaces(database):  # noqa: F811
    sync, _, _ = database
    repository = SoftwareRepository(
        software_repository_id="repo",
        project_id="p",
        name="API",
        base_path="/v1",
        repository_instance_url="https://git.example",
        repository_path="group/repo",
        created_by_user_id="u",
    )
    sync.add(repository)
    sync.flush()
    for interface_id, path in (("one", "/one"), ("two", "/two"), ("other", "/other")):
        sync.add(
            ApiInterface(
                interface_id=interface_id,
                software_repository_id="repo",
                name=interface_id,
                method="GET",
                path=path,
                path_key=path_key(path),
            )
        )
    task = sync.query(AiGenerateTask).filter_by(task_id="task").one()
    task.task_type = "api_case_generate"
    task.interface_ids_json = ["two", "one"]
    sync.commit()
    session = AsyncSessionAdapter(sync)
    source = await build_generate_run_snapshot(
        AiGenerateTaskRepository(session), "api", task, "attempt"
    )
    expected = fingerprint_root_input("api_interfaces", source)
    assert await lock_api_interface_root(session, task=task) == expected
    other = sync.query(ApiInterface).filter_by(interface_id="other").one()
    other.description = "unselected changed"
    sync.flush()
    assert await lock_api_interface_root(session, task=task) == expected
    selected = sync.query(ApiInterface).filter_by(interface_id="one").one()
    selected.description = "selected changed"
    sync.flush()
    assert (await lock_api_interface_root(session, task=task)).content_hash != expected.content_hash


async def test_ui_root_tracks_only_selected_cases_and_keeps_frozen_commit(database):  # noqa: F811
    sync, _, _ = database
    sync.add(FunctionTestSuite(suite_id="suite", requirement_id="req", name="suite"))
    sync.flush()
    for index, case_id in enumerate(("one", "two", "other")):
        sync.add(FunctionTestCase(case_id=case_id, suite_id="suite", title=case_id, order_no=index))
    task = sync.query(AiGenerateTask).filter_by(task_id="task").one()
    task.task_type = "ui_case_generate"
    sync.commit()
    session = AsyncSessionAdapter(sync)
    cases = await AiGenerateTaskRepository(session).list_ui_source_cases("req", ["two", "one"])
    frozen_source = {
        "taskId": task.task_id,
        "requirementId": "req",
        "uiSourceBatchId": "batch",
        "sourceRepository": {
            "repositoryId": "repo",
            "instanceUrl": "https://git.example",
            "pathWithNamespace": "group/repo",
            "branch": "main",
            "commit": "fixed-commit",
        },
        "functionalCases": cases,
    }
    expected = fingerprint_root_input("ui_repository_cases", frozen_source)
    root, locked_cases = await lock_ui_repository_cases_source(
        session, task=task, frozen_source=frozen_source
    )
    assert root == expected
    assert locked_cases == cases
    assert (
        await lock_ui_repository_cases_root(session, task=task, frozen_source=frozen_source)
        == expected
    )
    other = sync.query(FunctionTestCase).filter_by(case_id="other").one()
    other.title = "unselected changed"
    sync.flush()
    assert (
        await lock_ui_repository_cases_root(session, task=task, frozen_source=frozen_source)
        == expected
    )
    selected = sync.query(FunctionTestCase).filter_by(case_id="one").one()
    selected.title = "selected changed"
    sync.flush()
    changed_root, changed_cases = await lock_ui_repository_cases_source(
        session, task=task, frozen_source=frozen_source
    )
    assert changed_root.content_hash != expected.content_hash
    assert next(case for case in changed_cases if case["caseId"] == "one")["title"] == (
        "selected changed"
    )
    assert (
        await lock_ui_repository_cases_root(session, task=task, frozen_source=frozen_source)
    ).content_hash != expected.content_hash
