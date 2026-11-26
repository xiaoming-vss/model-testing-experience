"""Repository scope, locator templates and project rights of the element library."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.api_assets import add_member, make_software_repository
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.core.errors import AppError, ErrUiElementDuplicate
from testing_agent.models import Base
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.repositories.ui_element import UiElementRepository
from testing_agent.schemas.ui_element import UiElementCreate
from testing_agent.services.ui_element import UiElementService


def _assets(repo):
    return f"/v1/software-repositories/{repo}"


def _group(api, headers, repo):
    response = api.post(
        f"{_assets(repo)}/ui-element-groups",
        headers=headers,
        json={"name": "订单详情", "routeTemplate": "/orders/:id"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["groupId"]


def _template(**extra):
    return {
        "name": "编辑按钮",
        "scope": "指定订单行",
        "locatorType": "xpath",
        "locatorValue": "//tr[td[.={{orderNo|xpath}}]]//button",
        "parameters": [{"name": "orderNo", "description": "订单号"}],
        **extra,
    }


def test_group_reuse_template_and_versioned_maintenance(api):
    _, owner = account(api, "owner")
    repo = make_software_repository(api, owner, project(api, owner))
    group = _group(api, owner, repo)
    groups = f"{_assets(repo)}/ui-element-groups"
    elements = f"{_assets(repo)}/ui-elements"
    assert (
        api.post(
            groups, headers=owner, json={"name": "重名", "routeTemplate": "/orders/:id"}
        ).status_code
        == 409
    )
    created = api.post(elements, headers=owner, json=_template(groupId=group))
    assert created.status_code == 200, created.text
    detail = created.json()["data"]
    element = f"/v1/ui-elements/{detail['elementId']}"
    assert detail["parameterized"]
    assert detail["verificationStatus"] == "pending"
    assert detail["parameters"] == _template()["parameters"]
    assert detail["version"] == 1

    duplicate = api.post(elements, headers=owner, json=_template(groupId=group, name="另一名称"))
    assert duplicate.status_code == 409
    assert duplicate.json()["data"]["elementId"] == detail["elementId"]
    common = api.post(elements, headers=owner, json=_template())
    assert common.status_code == 200, common.text
    listed = api.get(groups, headers=owner).json()["data"]["items"]
    assert [(row["kind"], row["routeTemplate"], row["elementCount"]) for row in listed] == [
        ("common", "", 1),
        ("page", "/orders/:id", 1),
    ]

    filtered = api.get(
        elements, headers=owner, params={"groupId": group, "keyword": "orderNo", "pageSize": 1}
    ).json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["elementId"] == detail["elementId"]
    assert "locatorValue" not in filtered["items"][0]

    patch = api.patch(element, headers=owner, json={"version": 1, "name": "编辑订单"})
    assert patch.status_code == 200, patch.text
    assert patch.json()["data"]["version"] == 2
    assert api.delete(element, headers=owner, params={"version": 1}).status_code == 409
    assert api.delete(f"/v1/ui-element-groups/{group}", headers=owner).status_code == 409
    assert api.delete(_assets(repo), headers=owner).status_code == 409
    assert api.delete(element, headers=owner, params={"version": 2}).status_code == 200
    assert api.delete(f"/v1/ui-element-groups/{group}", headers=owner).status_code == 200


def test_scope_permissions_and_invalid_parameter_definitions(api):
    _, owner = account(api, "owner")
    viewer_user, viewer = account(api, "reader")
    _, outsider = account(api, "visitor")
    project_id = project(api, owner)
    add_member(api, owner, project_id, viewer_user["name"], "viewer")
    first = make_software_repository(api, owner, project_id)
    second = make_software_repository(api, owner, project_id, name="另一个应用")
    group = _group(api, owner, first)
    elements = f"{_assets(first)}/ui-elements"
    for invalid in (
        _template(parameters=[]),
        _template(locatorValue="//tr[td[.={{orderNo}}]]//button"),
        _template(locatorValue="//tr[td[.='{{orderNo|xpath}}']]//button"),
        _template(locatorType="role", locatorValue='{"role":"button","name":"{{orderNo}}"}'),
    ):
        assert api.post(elements, headers=owner, json=invalid).status_code == 400
    valid = api.post(elements, headers=owner, json=_template(groupId=group))
    assert valid.status_code == 200, valid.text
    element = f"/v1/ui-elements/{valid.json()['data']['elementId']}"
    assert api.get(element, headers=viewer).status_code == 200
    assert api.get(element, headers=outsider).status_code == 403
    assert (
        api.patch(element, headers=viewer, json={"version": 1, "name": "改名"}).status_code == 403
    )
    assert (
        api.post(
            f"{_assets(second)}/ui-elements", headers=owner, json=_template(groupId=group)
        ).status_code
        == 404
    )


@pytest.mark.asyncio
async def test_mysql_competing_public_element_writes_reuse_one_group(mysql):
    with mysql.begin() as conn:
        repo_id = seed_row(conn, Base.metadata.tables["software_repositories"])[
            "software_repository_id"
        ]
        actor = conn.exec_driver_sql(
            """SELECT p.user_id FROM projects AS p JOIN software_repositories AS r
               ON r.project_id = p.project_id WHERE r.software_repository_id = %s""",
            (repo_id,),
        ).scalar_one()

    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def save():
        async with sessions() as session:
            service = UiElementService(
                UiElementRepository(session), SoftwareRepositoryRepository(session)
            )
            return await service.create_element(
                actor, repo_id, UiElementCreate.model_validate(_template())
            )

    try:
        created, conflict = sorted(
            await asyncio.gather(save(), save(), return_exceptions=True),
            key=lambda result: isinstance(result, BaseException),
        )
        assert not isinstance(created, BaseException)
        assert isinstance(conflict, AppError)
        assert conflict.code == ErrUiElementDuplicate.code
        assert conflict.data == {"elementId": created.element_id}

        async with sessions() as session:
            service = UiElementService(
                UiElementRepository(session), SoftwareRepositoryRepository(session)
            )
            groups = await service.list_groups(actor, repo_id)
            assert groups.total == 1
            assert groups.items[0].element_count == 1
    finally:
        await engine.dispose()
