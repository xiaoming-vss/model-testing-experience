"""Project software repositories: CRUD, Git binding, ownership and deletion protection."""

from __future__ import annotations

import asyncio

import pytest
from support.api_assets import add_member, make_interface, make_software_repository
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, gitlab_connection, project
from support.project_api import api as api
from support.project_api import gitlab_remote as gitlab_remote

from testing_agent.models.requirement_software_repository import (
    RequirementSoftwareRepository,
)
from testing_agent.services.gitlab_queries import GitLabResources


def _connection(api, owner, project_id):
    return gitlab_connection(
        api, owner, project_id, f"owner-{project_id}", url="https://gitlab.example"
    )


@pytest.fixture
def gitlab_repository(api, gitlab_remote, monkeypatch):
    async def ensure_repository_scope(
        self, connection_id, project_id, group_id, repository_id, *, user_id
    ):
        return repository_id

    async def get_project(self, connection_id, project_id, repository_id, *, user_id):
        return {
            "pathWithNamespace": "commerce/order-service",
            "cloneUrl": "https://gitlab.example/commerce/order-service.git",
        }

    monkeypatch.setattr(GitLabResources, "ensure_repository_scope", ensure_repository_scope)
    monkeypatch.setattr(GitLabResources, "get_project", get_project)


def _create_repository(api, owner, project_id, connection_id, name="订单服务"):
    response = api.post(
        f"/v1/projects/{project_id}/software-repositories",
        headers=owner,
        json={
            "name": name,
            "description": "订单域",
            "basePath": "api/v2/",
            "repository": {
                "connectionId": connection_id,
                "groupId": "7",
                "repositoryId": "101",
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_owner_creates_repository_with_git_binding(api, gitlab_repository):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    connection_id = _connection(api, owner, pid)

    data = _create_repository(api, owner, pid, connection_id)
    assert data["name"] == "订单服务"
    assert data["description"] == "订单域"
    assert data["basePath"] == "/api/v2"
    assert data["repository"] == {
        "projectId": "101",
        "path": "commerce/order-service",
        "name": "order-service",
        "instanceUrl": "https://gitlab.example",
    }
    assert data["interfaceCount"] == 0
    assert data["version"] == 1

    listed = api.get(f"/v1/projects/{pid}/software-repositories", headers=owner).json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["softwareRepositoryId"] == data["softwareRepositoryId"]


def test_repository_is_required(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)

    response = api.post(
        f"/v1/projects/{pid}/software-repositories",
        headers=owner,
        json={"name": "订单服务"},
    )
    assert response.status_code == 400
    assert (
        api.post(
            f"/v1/projects/{pid}/software-repositories",
            headers=owner,
            json={"name": "订单服务", "repository": None},
        ).status_code
        == 400
    )


def test_repository_cannot_be_cleared(api, gitlab_repository):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    connection_id = _connection(api, owner, pid)
    repository = _create_repository(api, owner, pid, connection_id)

    response = api.patch(
        f"/v1/software-repositories/{repository['softwareRepositoryId']}",
        headers=owner,
        json={"repository": None},
    )
    assert response.status_code == 400
    assert response.json()["message"] == "软件仓库必须绑定 Git 仓库，不能清除"


def test_repository_name_is_unique_inside_project(api, gitlab_repository):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    other = project(api, owner, "另一个项目")
    connection_id = _connection(api, owner, pid)
    other_connection_id = _connection(api, owner, other)
    _create_repository(api, owner, pid, connection_id, "订单服务")

    response = api.post(
        f"/v1/projects/{pid}/software-repositories",
        headers=owner,
        json={
            "name": "订单服务",
            "repository": {
                "connectionId": connection_id,
                "groupId": "7",
                "repositoryId": "102",
            },
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3802

    assert (
        _create_repository(api, owner, other, other_connection_id, "订单服务")["name"] == "订单服务"
    )


def test_interface_count_and_deletion_protection(api, gitlab_repository):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    connection_id = _connection(api, owner, pid)
    repository = _create_repository(api, owner, pid, connection_id)
    repository_id = repository["softwareRepositoryId"]
    interface_id = make_interface(api, owner, repository_id)

    listed = api.get(f"/v1/projects/{pid}/software-repositories", headers=owner).json()["data"]
    assert listed["items"][0]["interfaceCount"] == 1
    detail = api.get(f"/v1/software-repositories/{repository_id}", headers=owner).json()["data"]
    assert detail["interfaceCount"] == 1

    response = api.delete(f"/v1/software-repositories/{repository_id}", headers=owner)
    assert response.status_code == 409
    assert response.json()["code"] == 3803

    assert api.delete(f"/v1/api-interfaces/{interface_id}", headers=owner).status_code == 200
    assert (
        api.delete(f"/v1/software-repositories/{repository_id}", headers=owner).status_code == 200
    )
    assert api.get(f"/v1/software-repositories/{repository_id}", headers=owner).status_code == 404


def test_requirement_association_blocks_deletion(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    repository_id = make_software_repository(api, owner, pid)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))

    async def associate():
        async with api.app.state.test_sessions() as session:
            session.add(
                RequirementSoftwareRepository(
                    requirement_id=requirement_id,
                    software_repository_id=repository_id,
                    branch="feature/order",
                    baseline_branch="main",
                    created_by_user_id="owner",
                )
            )
            await session.commit()

    asyncio.run(associate())
    response = api.delete(f"/v1/software-repositories/{repository_id}", headers=owner)
    assert response.status_code == 409
    assert response.json()["code"] == 3815


def test_member_and_viewer_cannot_manage_repositories(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    add_member(api, owner, pid, "member", "member")
    add_member(api, owner, pid, "viewer", "viewer")
    repository_id = make_software_repository(api, owner, pid)

    for headers in (member, viewer):
        assert (
            api.post(
                f"/v1/projects/{pid}/software-repositories",
                headers=headers,
                json={
                    "name": "新仓库",
                    "repository": {
                        "connectionId": "connection",
                        "groupId": "7",
                        "repositoryId": "101",
                    },
                },
            ).status_code
            == 403
        )
        assert (
            api.patch(
                f"/v1/software-repositories/{repository_id}",
                headers=headers,
                json={"name": "改名"},
            ).status_code
            == 403
        )
        assert (
            api.delete(f"/v1/software-repositories/{repository_id}", headers=headers).status_code
            == 403
        )

    assert api.get(f"/v1/projects/{pid}/software-repositories", headers=member).status_code == 200
    assert api.get(f"/v1/projects/{pid}/software-repositories", headers=viewer).status_code == 200


def test_repositories_are_project_scoped(api):
    _, owner = account(api, "owner")
    first = project(api, owner, "项目一")
    second = project(api, owner, "项目二")
    repository_id = make_software_repository(api, owner, first)

    assert api.get(f"/v1/software-repositories/{repository_id}", headers=owner).status_code == 200
    assert (
        api.get(f"/v1/projects/{second}/software-repositories", headers=owner).json()["data"][
            "total"
        ]
        == 0
    )


def test_project_delete_is_blocked_by_software_repository(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    repository_id = make_software_repository(api, owner, pid)

    blocked = api.delete(f"/v1/projects/{pid}", headers=owner)
    assert blocked.status_code == 409
    assert "software_repositories" in {
        item["resource"] for item in blocked.json()["data"]["blockers"]
    }

    assert (
        api.delete(f"/v1/software-repositories/{repository_id}", headers=owner).status_code == 200
    )
    assert api.delete(f"/v1/projects/{pid}", headers=owner).status_code == 200
