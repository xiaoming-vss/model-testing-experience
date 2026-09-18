from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testing_agent.api.deps import (
    get_current_user_id,
    get_project_skill_space_service,
)
from testing_agent.app import create_app
from testing_agent.services.project_skill_space import ProjectSkillSpaceService


class FakeProjectSkillRepository:
    session = None  # Owner-only fixture never queries non-owner memberships.

    def __init__(self):
        self.skill = None
        self.existing = None
        self.restored = None

    async def get_project(self, project_id: str):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    def add(self, skill):
        self.skill = skill

    async def commit(self):
        return None

    async def refresh(self, skill):
        return None

    async def get_active_by_project_and_filename(self, project_id: str, filename: str):
        return self.existing

    def restore(self, skill):
        self.restored = skill


@pytest.mark.asyncio
async def test_project_skill_defaults_storage_path_to_skill_storage_directory():
    repository = FakeProjectSkillRepository()
    service = ProjectSkillSpaceService(repository)

    await service.create("project-1", {"filename": "skills.zip"}, "user-1")

    assert repository.skill.storage_path.startswith("storage/skills/project-1/")
    assert repository.skill.storage_path.endswith("/skills.zip")


@pytest.mark.asyncio
async def test_project_skill_upload_updates_existing_active_filename():
    repository = FakeProjectSkillRepository()
    repository.existing = SimpleNamespace(
        skill_space_id="skill-1",
        project_id="project-1",
        version=1,
        hash="old",
        download_url="old",
        filename="skills.zip",
        size_bytes=3,
        storage_path="old-path",
        is_default=True,
        created_at=None,
        updated_at=None,
    )
    service = ProjectSkillSpaceService(repository)

    payload = await service.upload(
        "project-1",
        "skills.zip",
        b"new-content",
        "https://api.example.test",
        "user-1",
    )

    assert repository.existing.skill_space_id == "skill-1"
    assert repository.existing.version == 2
    assert repository.existing.is_default is False
    assert payload["skillSpaceId"] == "skill-1"


def test_project_skill_upload_endpoint_accepts_multipart_file():
    class FakeSkillService:
        async def upload(self, project_id, filename, content, public_base_url, user_id):
            assert project_id == "project-1"
            assert filename == "skills.zip"
            assert content == b"zip-content"
            assert public_base_url == "https://cdn.example.test"
            assert user_id == "user-1"
            return {"skillSpaceId": "skill-1", "projectId": project_id}

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_project_skill_space_service] = lambda: FakeSkillService()
    client = TestClient(app)

    response = client.post(
        "/v1/projects/project-1/skills",
        files={"file": ("skills.zip", b"zip-content", "application/zip")},
        data={"publicBaseURL": "https://cdn.example.test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"]["skillSpaceId"] == "skill-1"
    assert payload["data"]["projectId"] == "project-1"


def test_project_skill_list_endpoint_keeps_success_envelope():
    class FakeSkillService:
        async def list(self, project_id, user_id):
            assert project_id == "project-1"
            assert user_id == "user-1"
            return [
                {
                    "skillSpaceId": "skill-1",
                    "projectId": project_id,
                    "version": 1,
                    "hash": "hash",
                    "downloadUrl": "/v1/projects/project-1/skills/skill-1/download",
                    "filename": "skills.zip",
                    "size": 11,
                    "isDefault": False,
                    "createdAt": None,
                    "updatedAt": None,
                }
            ]

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_project_skill_space_service] = lambda: FakeSkillService()
    client = TestClient(app)

    response = client.get("/v1/projects/project-1/skills")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["message"] == "ok"
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["items"][0]["skillSpaceId"] == "skill-1"


def test_project_skill_download_endpoint_is_public():
    class FakeSkillService:
        async def get_download_public(self, project_id, skill_space_id):
            assert project_id == "project-1"
            assert skill_space_id == "skill-1"
            return SimpleNamespace(
                storage_path="",
                filename="skills.zip",
                content=b"zip-content",
                skill_space_id="skill-1",
                project_id=project_id,
                version=1,
                hash="hash",
                download_url="",
                size_bytes=11,
                is_default=False,
                created_at=None,
                updated_at=None,
            )

    app = create_app()
    app.dependency_overrides[get_project_skill_space_service] = lambda: FakeSkillService()
    client = TestClient(app)

    response = client.get("/v1/projects/project-1/skills/skill-1/download")

    assert response.status_code == 200
    assert response.content == b"zip-content"
