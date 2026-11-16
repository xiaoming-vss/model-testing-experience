"""Requirement-to-software-repository association API.

Requirements no longer bind GitLab repositories directly. Each association
stores its own working branch and baseline branch.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from support.api_assets import add_member, make_software_repository
from support.project_api import account, project, requirement
from support.project_api import api as api

from testing_agent.models.requirement_software_repository import (
    RequirementSoftwareRepository,
)
from testing_agent.services.integration_connection import IntegrationConnectionService


@pytest.fixture
def gitlab_branches(monkeypatch):
    async def resolve_personal_connection(
        self, user_id, provider, project_id, instance_url, connection_id=""
    ):
        return SimpleNamespace(connection_id="connection-1", base_url=instance_url)

    async def get_gitlab_branch(self, connection_id, project_id, repository_id, branch, *, user_id):
        return {"name": branch}

    monkeypatch.setattr(
        IntegrationConnectionService, "resolve_personal_connection", resolve_personal_connection
    )
    monkeypatch.setattr(IntegrationConnectionService, "get_gitlab_branch", get_gitlab_branch)


def _create(api, headers, requirement_id, repository_id, **overrides):
    body = {
        "softwareRepositoryId": repository_id,
        "branch": "feature/order",
        "baselineBranch": "main",
        **overrides,
    }
    return api.post(
        f"/v1/requirements/{requirement_id}/software-repositories",
        headers=headers,
        json=body,
    )


def test_association_lifecycle_and_project_visibility(api, gitlab_branches):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    add_member(api, owner, pid, "member", "member")
    requirement_id = requirement(api, owner, pid)
    repository_id = make_software_repository(api, owner, pid)

    created = _create(api, owner, requirement_id, repository_id, branch="feature/order-v1")
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["softwareRepositoryId"] == repository_id
    assert data["softwareRepositoryName"] == "支付网关"
    assert data["branch"] == "feature/order-v1"
    assert data["baselineBranch"] == "main"
    assert data["repository"]["path"] == "commerce/支付网关"

    listed = api.get(
        f"/v1/requirements/{requirement_id}/software-repositories", headers=member
    ).json()["data"]
    assert listed["total"] == 1

    updated = api.patch(
        f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
        headers=member,
        json={"branch": "feature/order-v2", "baselineBranch": "release-1.0"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["branch"] == "feature/order-v2"
    assert updated.json()["data"]["baselineBranch"] == "release-1.0"

    deleted = api.delete(
        f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
        headers=member,
    )
    assert deleted.status_code == 200
    assert (
        api.get(f"/v1/requirements/{requirement_id}/software-repositories", headers=owner).json()[
            "data"
        ]["total"]
        == 0
    )


def test_branch_and_baseline_are_required_and_must_differ(api, gitlab_branches):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    repository_id = make_software_repository(api, owner, pid)

    assert _create(api, owner, requirement_id, repository_id, branch="").status_code == 400
    assert _create(api, owner, requirement_id, repository_id, baselineBranch="").status_code == 400
    response = _create(
        api, owner, requirement_id, repository_id, branch="main", baselineBranch="main"
    )
    assert response.status_code == 400
    assert response.json()["message"] == "基线分支不能与工作分支相同"


def test_duplicate_association_is_rejected(api, gitlab_branches):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    repository_id = make_software_repository(api, owner, pid)

    assert _create(api, owner, requirement_id, repository_id).status_code == 200
    duplicate = _create(api, owner, requirement_id, repository_id)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 3817


def test_software_repository_must_belong_to_requirement_project(api, gitlab_branches):
    _, owner = account(api, "owner")
    first = project(api, owner, "项目一")
    second = project(api, owner, "项目二")
    requirement_id = requirement(api, owner, first)
    foreign_repository = make_software_repository(api, owner, second)

    response = _create(api, owner, requirement_id, foreign_repository)
    assert response.status_code == 404


def test_viewer_can_read_but_not_write(api, gitlab_branches):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    add_member(api, owner, pid, "viewer", "viewer")
    requirement_id = requirement(api, owner, pid)
    repository_id = make_software_repository(api, owner, pid)
    _create(api, owner, requirement_id, repository_id)

    assert (
        api.get(
            f"/v1/requirements/{requirement_id}/software-repositories", headers=viewer
        ).status_code
        == 200
    )
    assert _create(api, viewer, requirement_id, repository_id, branch="other").status_code == 403
    assert (
        api.patch(
            f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
            headers=viewer,
            json={"branch": "other"},
        ).status_code
        == 403
    )
    assert (
        api.delete(
            f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
            headers=viewer,
        ).status_code
        == 403
    )


def test_branches_cleared_by_rebind_can_be_restored_one_at_a_time(api, gitlab_branches):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = requirement(api, owner, pid)
    repository_id = make_software_repository(api, owner, pid)
    _create(api, owner, requirement_id, repository_id)

    async def clear_branches():
        async with api.app.state.test_sessions() as session:
            await session.execute(
                update(RequirementSoftwareRepository)
                .where(
                    RequirementSoftwareRepository.requirement_id == requirement_id,
                    RequirementSoftwareRepository.software_repository_id == repository_id,
                )
                .values(branch="", baseline_branch="")
            )
            await session.commit()

    asyncio.run(clear_branches())

    branch_only = api.patch(
        f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
        headers=owner,
        json={"branch": "feature/restored"},
    )
    assert branch_only.status_code == 200, branch_only.text
    assert branch_only.json()["data"]["branch"] == "feature/restored"
    assert branch_only.json()["data"]["baselineBranch"] == ""

    baseline_only = api.patch(
        f"/v1/requirements/{requirement_id}/software-repositories/{repository_id}",
        headers=owner,
        json={"baselineBranch": "main"},
    )
    assert baseline_only.status_code == 200, baseline_only.text
    assert baseline_only.json()["data"]["branch"] == "feature/restored"
    assert baseline_only.json()["data"]["baselineBranch"] == "main"
