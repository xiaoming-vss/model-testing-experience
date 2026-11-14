"""Project interface definitions: CRUD, identity, associations and permissions."""

from urllib.parse import urlencode

from support.api_assets import add_member, interface_body, make_app, make_interface
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project
from support.project_api import api as api


def _list(api, headers, project_id, **params):
    query = urlencode({key: value for key, value in params.items() if value not in ("", None)})
    suffix = f"?{query}" if query else ""
    response = api.get(f"/v1/projects/{project_id}/api-interfaces{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _list_app(api, headers, app_id, **params):
    query = urlencode({key: value for key, value in params.items() if value not in ("", None)})
    suffix = f"?{query}" if query else ""
    response = api.get(f"/v1/api-apps/{app_id}/interfaces{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_developer_cannot_access_interface_library(api):
    _, owner = account(api, "owner")
    _, developer = account(api, "developer")
    pid = project(api, owner)
    add_member(api, owner, pid, "developer", "developer")
    app_id = make_app(api, owner, pid)

    assert api.get(f"/v1/projects/{pid}/api-apps", headers=developer).status_code == 403
    assert api.get(f"/v1/api-apps/{app_id}", headers=developer).status_code == 403
    assert api.get(f"/v1/projects/{pid}/api-interfaces", headers=developer).status_code == 403


def test_create_and_get_interface_round_trip(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid, basePath="/api/v2")
    interface_id = make_interface(
        api,
        owner,
        app_id,
        path="/orders/{orderId}",
        pathParams=[
            {
                "enabled": True,
                "name": "orderId",
                "type": "string",
                "required": True,
                "example": "o-1",
                "description": "订单号",
            }
        ],
        queryParams=[
            {
                "enabled": True,
                "name": "include",
                "type": "string",
                "required": False,
                "example": "items",
                "description": "",
            }
        ],
    )

    data = api.get(f"/v1/api-interfaces/{interface_id}", headers=owner).json()["data"]
    assert data["appId"] == app_id
    assert data["appName"] == "支付网关"
    assert data["path"] == "/orders/{orderId}"
    assert data["pathParams"][0]["name"] == "orderId"
    assert data["queryParams"][0]["example"] == "items"
    assert data["headers"][0]["name"] == "Authorization"
    assert data["bodyType"] == "json"
    assert data["bodySchema"] == {"type": "object"}
    assert data["source"]["type"] == "manual"
    assert data["version"] == 1
    assert data["requirements"] == []


def test_identity_normalizes_method_and_trailing_slash(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    make_interface(api, owner, app_id, method="post", path="/orders/")

    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces",
        headers=owner,
        json=interface_body(method="POST", path="/orders"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3805


def test_path_parameters_must_match_path_placeholders(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)

    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces",
        headers=owner,
        json=interface_body(path="/orders/{orderId}"),
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3813

    interface_id = make_interface(
        api,
        owner,
        app_id,
        path="/orders/{orderId}",
        pathParams=[
            {
                "enabled": True,
                "name": "orderId",
                "type": "string",
                "required": True,
                "example": "",
                "description": "",
            }
        ],
    )
    response = api.patch(
        f"/v1/api-interfaces/{interface_id}",
        headers=owner,
        json={"path": "/orders/{orderId}/items/{itemId}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3813


def test_requirements_are_optional_and_sprint_filter_uses_requirement(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    req_a = make_requirement(api, owner, sprint_a, "需求A")
    req_b = make_requirement(api, owner, sprint_b, "需求B")
    app_id = make_app(api, owner, pid)

    first = make_interface(api, owner, app_id, requirementIds=[req_a], path="/a")
    second = make_interface(api, owner, app_id, requirementIds=[req_b], path="/b")
    make_interface(api, owner, app_id, path="/c")

    assert _list(api, owner, pid, sprintId=sprint_a)["total"] == 1
    assert _list(api, owner, pid, sprintId=sprint_b)["total"] == 1
    assert _list(api, owner, pid, requirementId=req_a)["total"] == 1
    assert _list(api, owner, pid, requirementId=req_a)["items"][0]["interfaceId"] == first
    assert _list(api, owner, pid, requirementId=req_b)["items"][0]["interfaceId"] == second

    detail = api.get(f"/v1/api-interfaces/{first}", headers=owner).json()["data"]
    assert detail["requirements"] == [
        {
            "requirementId": req_a,
            "name": "需求A",
            "sprintId": sprint_a,
            "sprintName": "迭代A",
        }
    ]


def test_requirement_from_another_project_is_rejected(api):
    _, owner = account(api, "owner")
    pid = project(api, owner, "项目一")
    other = project(api, owner, "项目二")
    other_req = make_requirement(api, owner, make_sprint(api, owner, other))
    app_id = make_app(api, owner, pid)

    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces",
        headers=owner,
        json=interface_body(requirementIds=[other_req]),
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3810


def test_member_can_write_and_viewer_can_only_read(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    add_member(api, owner, pid, "member", "member")
    add_member(api, owner, pid, "viewer", "viewer")
    app_id = make_app(api, owner, pid)

    interface_id = make_interface(api, member, app_id)
    assert api.get(f"/v1/api-interfaces/{interface_id}", headers=viewer).status_code == 200
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces",
        headers=viewer,
        json=interface_body(path="/viewer"),
    )
    assert response.status_code == 403
    assert (
        api.patch(
            f"/v1/api-interfaces/{interface_id}",
            headers=viewer,
            json={"name": "改名"},
        ).status_code
        == 403
    )
    assert api.delete(f"/v1/api-interfaces/{interface_id}", headers=viewer).status_code == 403


def test_list_filters_pagination_and_stable_total(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    for index in range(5):
        make_interface(api, owner, app_id, name=f"接口{index}", path=f"/items/{index}")

    first = _list(api, owner, pid, page=1, pageSize=2)
    second = _list(api, owner, pid, page=2, pageSize=2)
    third = _list(api, owner, pid, page=3, pageSize=2)
    assert first["total"] == 5
    assert [len(page["items"]) for page in (first, second, third)] == [2, 2, 1]
    assert _list(api, owner, pid, keyword="接口1")["total"] == 1
    assert _list(api, owner, pid, keyword="items/3")["total"] == 1
    assert _list(api, owner, pid, method="POST")["total"] == 5
    assert _list(api, owner, pid, method="GET")["total"] == 0

    app_list = _list_app(api, owner, app_id, page=1, pageSize=2)
    assert app_list["total"] == 5
    assert len(app_list["items"]) == 2


def test_quick_toggle_and_update_bump_version(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    interface_id = make_interface(api, owner, app_id)

    data = api.patch(
        f"/v1/api-interfaces/{interface_id}", headers=owner, json={"enabled": False}
    ).json()["data"]
    assert data["enabled"] is False
    assert data["version"] == 2

    data = api.patch(
        f"/v1/api-interfaces/{interface_id}",
        headers=owner,
        json={"name": "创建订单 V2", "tags": ["订单", "支付"]},
    ).json()["data"]
    assert data["name"] == "创建订单 V2"
    assert data["tags"] == ["订单", "支付"]
    assert data["version"] == 3

    same = api.patch(
        f"/v1/api-interfaces/{interface_id}",
        headers=owner,
        json={"name": "创建订单 V2"},
    ).json()["data"]
    assert same["version"] == 3


def test_delete_is_hard_and_releases_identity(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    interface_id = make_interface(api, owner, app_id)

    assert api.delete(f"/v1/api-interfaces/{interface_id}", headers=owner).status_code == 200
    assert api.get(f"/v1/api-interfaces/{interface_id}", headers=owner).status_code == 404
    make_interface(api, owner, app_id)


def test_app_id_is_immutable_on_patch(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    other_app = make_app(api, owner, pid, "另一个应用")
    interface_id = make_interface(api, owner, app_id)

    response = api.patch(
        f"/v1/api-interfaces/{interface_id}",
        headers=owner,
        json={"appId": other_app},
    )
    assert response.status_code == 400
