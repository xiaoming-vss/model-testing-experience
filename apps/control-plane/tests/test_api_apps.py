"""Project interface applications: CRUD, ownership and deletion protection."""

from support.api_assets import add_member, make_app, make_interface
from support.project_api import account, project
from support.project_api import api as api


def test_owner_can_manage_apps_and_counts(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid, "订单服务", basePath="api/v2/")

    data = api.get(f"/v1/api-apps/{app_id}", headers=owner).json()["data"]
    assert data["name"] == "订单服务"
    assert data["basePath"] == "/api/v2"
    assert data["enabled"] is True
    assert data["version"] == 1
    assert data["interfaceCount"] == 0

    make_interface(api, owner, app_id)
    apps = api.get(f"/v1/projects/{pid}/api-apps", headers=owner).json()["data"]
    assert apps["total"] == 1
    assert apps["items"][0]["interfaceCount"] == 1
    assert apps["items"][0]["enabledInterfaceCount"] == 1


def test_app_name_is_unique_inside_project(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    other = project(api, owner, "另一个项目")
    make_app(api, owner, pid, "订单服务")
    response = api.post(
        f"/v1/projects/{pid}/api-apps",
        headers=owner,
        json={"name": "订单服务"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3802
    make_app(api, owner, other, "订单服务")


def test_app_delete_is_blocked_until_interfaces_are_removed(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    interface_id = make_interface(api, owner, app_id)

    response = api.delete(f"/v1/api-apps/{app_id}", headers=owner)
    assert response.status_code == 409
    assert response.json()["code"] == 3803

    assert api.delete(f"/v1/api-interfaces/{interface_id}", headers=owner).status_code == 200
    assert api.delete(f"/v1/api-apps/{app_id}", headers=owner).status_code == 200
    assert api.get(f"/v1/api-apps/{app_id}", headers=owner).status_code == 404


def test_app_disable_does_not_change_interface_status(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    interface_id = make_interface(api, owner, app_id)

    data = api.patch(f"/v1/api-apps/{app_id}", headers=owner, json={"enabled": False}).json()[
        "data"
    ]
    assert data["enabled"] is False
    assert data["version"] == 2

    interface = api.get(f"/v1/api-interfaces/{interface_id}", headers=owner).json()["data"]
    assert interface["enabled"] is True


def test_member_and_viewer_cannot_manage_apps(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    add_member(api, owner, pid, "member", "member")
    add_member(api, owner, pid, "viewer", "viewer")
    app_id = make_app(api, owner, pid)

    for headers in (member, viewer):
        response = api.post(
            f"/v1/projects/{pid}/api-apps", headers=headers, json={"name": "新应用"}
        )
        assert response.status_code == 403
        assert (
            api.patch(f"/v1/api-apps/{app_id}", headers=headers, json={"name": "改名"}).status_code
            == 403
        )
        assert api.delete(f"/v1/api-apps/{app_id}", headers=headers).status_code == 403

    assert api.get(f"/v1/projects/{pid}/api-apps", headers=member).status_code == 200
    assert api.get(f"/v1/projects/{pid}/api-apps", headers=viewer).status_code == 200


def test_apps_are_project_scoped(api):
    _, owner = account(api, "owner")
    first = project(api, owner, "项目一")
    second = project(api, owner, "项目二")
    app_id = make_app(api, owner, first)

    assert api.get(f"/v1/api-apps/{app_id}", headers=owner).status_code == 200
    assert api.get(f"/v1/projects/{second}/api-apps", headers=owner).json()["data"]["total"] == 0


def test_app_update_normalizes_base_path_and_clears_repository(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid, basePath="/api/v1")
    data = api.patch(
        f"/v1/api-apps/{app_id}",
        headers=owner,
        json={"basePath": "", "repository": None},
    ).json()["data"]
    assert data["basePath"] == ""
    assert data["repository"] is None


def test_project_delete_is_blocked_by_api_app(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)

    blocked = api.delete(f"/v1/projects/{pid}", headers=owner)
    assert blocked.status_code == 409
    assert "api_apps" in {item["resource"] for item in blocked.json()["data"]["blockers"]}

    assert api.delete(f"/v1/api-apps/{app_id}", headers=owner).status_code == 200
    assert api.delete(f"/v1/projects/{pid}", headers=owner).status_code == 200
