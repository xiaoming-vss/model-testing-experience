from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from support.deletion import MemoryResourceDeletion

from testing_agent.app import create_app
from testing_agent.schemas.requirement import CreateRequirementRequest, UpdateRequirementRequest
from testing_agent.services.requirement import RequirementService


class FakeRequirementRepository:
    def __init__(self):
        self.session = None
        self.requirement = None
        self.existing = None
        self.restored = None

    async def get_active_by_sprint_and_name(self, sprint_id, name):
        if self.existing is not None:
            return self.existing
        return None

    async def get_by_sprint_and_name_unscoped(self, sprint_id, name):
        return self.existing

    async def get_active_by_id(self, requirement_id):
        return self.requirement

    def add(self, requirement):
        self.requirement = requirement

    def restore(self, requirement):
        self.restored = requirement
        self.requirement = requirement

    async def commit(self):
        return None

    async def refresh(self, requirement):
        return None

    async def hard_delete(self, requirement):
        self.requirement = None
        self.existing = None


class FakeSprintService:
    async def get_accessible_entity(self, user_id, sprint_id, *, action="read"):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")


class FakeFiles:
    async def attach(self, user, file_id, project, resource, resource_id, *, purpose):
        assert project == "project-1"
        return SimpleNamespace(file_id=file_id, filename="requirement.docx", sha256="hash")


@pytest.mark.asyncio
async def test_s3_source_survives_enhanced_content_update_and_hard_delete():
    repository = FakeRequirementRepository()
    service = RequirementService(
        repository,
        FakeSprintService(),
        files=FakeFiles(),
        deletion=MemoryResourceDeletion(repository),
    )
    body = CreateRequirementRequest(name="Login", documentType="word", documentFileId="file-1")
    payload = await service.create("user-1", "sprint-1", body)
    assert payload["documentContent"] == ""
    assert payload["documentFileId"] == "file-1"
    updated = await service.update(
        "user-1",
        payload["requirementId"],
        UpdateRequirementRequest(documentContent="enhanced text"),
    )
    assert updated["documentContent"] == "enhanced text"
    assert updated["documentFileId"] == "file-1"
    assert updated["documentHash"] == "hash"
    await service.delete("user-1", payload["requirementId"])
    recreated = await service.create("user-1", "sprint-1", body)
    assert recreated["requirementId"] != payload["requirementId"]


@pytest.mark.asyncio
async def test_inline_source_creation_is_rejected():
    from testing_agent.core.errors import AppError

    repository = FakeRequirementRepository()
    service = RequirementService(repository, FakeSprintService())
    with pytest.raises(AppError, match="S3"):
        await service.create(
            "user", "sprint", CreateRequirementRequest(name="r", documentContent="source")
        )
    assert repository.requirement is None


@pytest.mark.asyncio
async def test_existing_local_file_and_inline_content_are_not_download_fallbacks(tmp_path):
    from testing_agent.core.errors import AppError
    from testing_agent.services.ai_task_output import requirement_source_content

    path = tmp_path / "original.txt"
    path.write_text("old source")
    repository = FakeRequirementRepository()
    repository.requirement = SimpleNamespace(
        sprint_id="sprint",
        document_file_id="",
        document_content="",
    )
    service = RequirementService(repository, FakeSprintService())
    assert requirement_source_content(repository.requirement) == ""
    for content in ("", "enhanced text"):
        repository.requirement.document_content = content
        with pytest.raises(AppError, match="重新上传"):
            await service.get_download("user", "requirement")
    assert path.read_text() == "old source"


def test_local_upload_routes_are_removed():
    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert "/v1/sprints/{sprint_id}/requirements/upload" not in paths
    assert "/v1/requirements/{requirement_id}/document" not in paths


def test_requirement_request_validates_document_types():
    with pytest.raises(ValidationError):
        CreateRequirementRequest(name="r", documentType="unsupported")
    assert CreateRequirementRequest(name="r", documentType="word").document_type == "docx"
