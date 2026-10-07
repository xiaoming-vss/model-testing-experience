"""Business deletion must close both metadata and fresh download authorization."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import httpx
import pytest
from test_stored_files import files as files
from test_stored_files import upload

from testing_agent.api.deps import (
    get_current_user_id,
    get_file_service,
    get_requirement_service,
)
from testing_agent.app import create_app
from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.bug import Bug
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.services.project import ProjectService
from testing_agent.services.requirement import RequirementService
from testing_agent.services.sprint import SprintService
from testing_agent.services.stored_file import utcnow


async def linked_file(files, kind, *, suite_run=False):
    entities = {}
    if kind in {"requirement", "ui_worker_task"}:
        entities["sprint"] = Sprint(
            sprint_id="access-s",
            project_id="p",
            name="access",
            start_time=utcnow(),
            end_time=utcnow() + timedelta(days=1),
        )
        entities["requirement"] = Requirement(
            requirement_id="access-r",
            sprint_id="access-s",
            name="access",
        )
    if kind == "bug":
        entities[kind] = Bug(
            bug_id="access-b",
            project_id="p",
            bug_no=10,
            title="access",
            found_sprint_id="deleted-sprint",
        )
        resource_id, purpose = "access-b", "attachment"
    elif kind == "requirement":
        resource_id, purpose = "access-r", "requirement"
    elif kind == "ui_source_archive":
        entities["task"] = AiGenerateTask(
            task_id="access-task",
            project_id="p",
            task_type="ui_case_generate",
            sprint_id="s",
            requirement_id="r",
            name="access",
            creator_user_id="owner",
            source_type="source_archive",
            source_content="",
        )
        resource_id, purpose = "access-task", kind
    elif kind == "project_skill":
        entities["skill"] = ProjectSkillSpace(
            skill_space_id="access-skill",
            project_id="p",
            scope_key="p",
            filename="access",
            hash="hash",
            manifest=[],
        )
        resource_id, purpose = "access-skill", kind
    elif kind == "ui_worker_task":
        entities["suite"] = UiTestSuite(
            suite_id="access-suite",
            requirement_id="access-r",
            name="access",
        )
        entities["case"] = UiTestCase(
            case_id="access-case",
            suite_id="access-suite",
            name="access",
            steps_json=[],
        )
        entities["run"] = (
            UiTestSuiteRun(
                suite_run_id="access-run",
                suite_id="access-suite",
                trigger_user_id="owner",
                status="success",
            )
            if suite_run
            else UiTestCaseRun(
                run_id="access-run",
                suite_id="access-suite",
                case_id="access-case",
                trigger_user_id="owner",
                status="success",
            )
        )
        entities["queue"] = WorkerTask(
            domain="ui",
            task_id="access-queue",
            run_id="access-run",
            task_type="suite_run" if suite_run else "case_debug",
            status="success",
        )
        resource_id, purpose = "access-queue", "ui_artifact"
    files.session.add_all(entities.values())
    await files.session.commit()
    if purpose == "ui_source_archive":
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("source.js", "test")
        content, filename = buffer.getvalue(), "source.zip"
    elif purpose == "ui_artifact":
        content, filename = b"\x89PNG\r\n\x1a\nimage", "evidence.png"
    else:
        content, filename = b"evidence", "evidence.txt"
    row, _ = await upload(files, content, filename, purpose)
    await files.complete("owner", row.file_id)
    await files.attach("owner", row.file_id, "p", kind, resource_id, purpose=purpose)
    if kind == "requirement":
        entities[kind].document_file_id = row.file_id
    if kind == "project_skill":
        entities["skill"].manifest = [{"fileId": row.file_id, "path": filename}]
    await files.session.commit()
    return row, entities


@pytest.mark.parametrize(
    "kind,removed",
    [
        ("requirement", "requirement"),
        ("requirement", "sprint"),
        ("bug", "bug"),
        ("ui_source_archive", "task"),
        ("project_skill", "skill"),
        ("ui_worker_task", "queue"),
        ("ui_worker_task", "run"),
        ("ui_worker_task", "case"),
        ("ui_worker_task", "suite"),
        ("ui_worker_task", "requirement"),
        ("ui_worker_task", "sprint"),
    ],
)
async def test_deleted_business_blocks_metadata_and_new_ticket(files, kind, removed, monkeypatch):
    row, entities = await linked_file(files, kind)
    assert (await files.download("viewer", row.file_id))["sha256"] == row.sha256
    await files.session.delete(entities[removed])
    await files.session.commit()
    signer = Mock(side_effect=AssertionError("Must reject before signing"))
    monkeypatch.setattr(files.storage, "download_ticket", signer)
    for operation in (files.metadata, files.download):
        with pytest.raises(AppError) as rejected:
            await operation("viewer", row.file_id)
        assert rejected.value.http_code == 404
    # Worker-facing ticket creation shares the same business validity check.
    with pytest.raises(AppError) as rejected:
        await files.ticket(row)
    assert rejected.value.http_code == 404
    signer.assert_not_called()
    # Denying access does not physically delete any historical bytes.
    assert files.storage.client.head_object(Bucket=row.bucket, Key=row.object_key)["ContentLength"]


async def test_requirement_delete_api_closes_both_download_routes(files):
    row, _ = await linked_file(files, "requirement")
    service = RequirementService(
        RequirementRepository(files.session),
        SprintService(
            SprintRepository(files.session),
            ProjectService(ProjectRepository(files.session)),
        ),
        files=files,
    )
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "owner"
    app.dependency_overrides[get_file_service] = lambda: files
    app.dependency_overrides[get_requirement_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        routes = ["/v1/requirements/access-r/download", f"/v1/files/{row.file_id}/download"]
        for route in routes:
            assert (
                await client.get(route, headers={"Accept": "application/json"})
            ).status_code == 200
        assert (await client.delete("/v1/requirements/access-r")).status_code == 200
        for route in routes + [f"/v1/files/{row.file_id}"]:
            assert (
                await client.get(route, headers={"Accept": "application/json"})
            ).status_code == 404


@pytest.mark.parametrize(
    "kind", ["requirement", "bug", "ui_source_archive", "project_skill", "ui_worker_task"]
)
async def test_mismatched_business_project_is_not_readable(files, kind):
    row, entities = await linked_file(files, kind)
    entity = (
        entities.get("sprint") or entities.get("bug") or entities.get("task") or entities["skill"]
    )
    entity.project_id = "q"
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("viewer", row.file_id)
    assert rejected.value.http_code == 404


@pytest.mark.parametrize("kind", ["requirement", "bug", "ui_source_archive"])
async def test_retained_history_remains_readable(files, kind):
    row, entities = await linked_file(files, kind)
    if kind == "requirement":
        entities[kind].document_file_id = "replacement-file"
    elif kind == "bug":
        row.status = "archived"
        entities[kind].description_html = "<p>removed image</p>"
    row.expires_at = utcnow() - timedelta(days=1)
    await files.session.commit()
    assert (await files.download("viewer", row.file_id))["sha256"] == row.sha256


async def test_skill_file_removed_from_manifest_is_not_readable(files):
    row, entities = await linked_file(files, "project_skill")
    entities["skill"].manifest = []
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("viewer", row.file_id)
    assert rejected.value.http_code == 404


async def test_finished_suite_artifact_readable_until_run_deleted(files):
    row, entities = await linked_file(files, "ui_worker_task", suite_run=True)
    assert (await files.download("viewer", row.file_id))["size"] == row.size
    await files.session.delete(entities["run"])
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("viewer", row.file_id)
    assert rejected.value.http_code == 404


async def test_unknown_binding_fails_closed(files):
    row, _ = await linked_file(files, "bug")
    row.resource_type = "unknown"
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("owner", row.file_id)
    assert rejected.value.http_code == 404


@pytest.mark.parametrize("changed", ["empty_id", "wrong_purpose", "wrong_domain", "wrong_run_type"])
async def test_invalid_binding_is_not_readable(files, changed):
    row, entities = await linked_file(files, "ui_worker_task")
    if changed == "empty_id":
        row.resource_id = ""
    elif changed == "wrong_purpose":
        row.purpose = "requirement"
    elif changed == "wrong_domain":
        entities["queue"].domain = "api"
    else:
        entities["queue"].task_type = "unknown"
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("viewer", row.file_id)
    assert rejected.value.http_code == 404


async def test_role_change_rechecks_current_permission_for_history(files):
    row, _ = await linked_file(files, "requirement")
    # Select by business key, independent of primary-key assignment.
    from sqlalchemy import select

    member = await files.session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == "p",
            ProjectMember.user_id == "member",
        )
    )
    assert (await files.download("member", row.file_id))["size"] == row.size
    member.role = "developer"
    await files.session.commit()
    with pytest.raises(AppError) as rejected:
        await files.download("member", row.file_id)
    assert rejected.value.http_code == 403
