"""Interface library tag-group operations: rename, removal and interface moves."""

from support.api_assets import add_member, make_interface, make_software_repository
from support.project_api import account, project
from support.project_api import api as api


def _detail(api, headers, interface_id):
    response = api.get(f"/v1/api-interfaces/{interface_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_rename_group_replaces_only_the_first_tag(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    first = make_interface(
        api,
        owner,
        software_repository_id,
        name="查询订单列表",
        method="GET",
        path="/orders",
        tags=["订单", "查询"],
    )
    second = make_interface(
        api,
        owner,
        software_repository_id,
        name="创建订单",
        method="POST",
        path="/orders",
        tags=["订单"],
    )
    other = make_interface(
        api,
        owner,
        software_repository_id,
        name="账户列表",
        method="GET",
        path="/accounts",
        tags=["账户"],
    )

    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "订单", "newGroupName": " 订单管理 "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "groupName": "订单",
        "newGroupName": "订单管理",
        "updatedCount": 2,
    }

    first_data = _detail(api, owner, first)
    assert first_data["tags"] == ["订单管理", "查询"]
    assert first_data["version"] == 2
    second_data = _detail(api, owner, second)
    assert second_data["tags"] == ["订单管理"]
    assert second_data["version"] == 2
    other_data = _detail(api, owner, other)
    assert other_data["tags"] == ["账户"]
    assert other_data["version"] == 1

    same = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "订单管理", "newGroupName": "订单管理"},
    )
    assert same.status_code == 200, same.text
    assert same.json()["data"]["updatedCount"] == 0
    assert _detail(api, owner, first)["version"] == 2


def test_rename_group_rejects_existing_missing_and_reserved_names(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    make_interface(api, owner, software_repository_id, path="/orders", tags=["订单"])
    make_interface(api, owner, software_repository_id, path="/accounts", tags=["账户"])

    conflict = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "订单", "newGroupName": "账户"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 3819

    missing = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "不存在", "newGroupName": "新分组"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 3818

    reserved = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "订单", "newGroupName": "未分类"},
    )
    assert reserved.status_code == 400
    assert reserved.json()["message"] == "分组名称不能为「未分类」"


def test_delete_group_clears_all_tags_and_keeps_interfaces(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    first = make_interface(
        api,
        owner,
        software_repository_id,
        method="GET",
        path="/orders",
        tags=["订单", "查询"],
    )
    second = make_interface(
        api,
        owner,
        software_repository_id,
        method="POST",
        path="/orders",
        tags=["订单"],
    )
    other = make_interface(
        api,
        owner,
        software_repository_id,
        method="GET",
        path="/accounts",
        tags=["账户"],
    )

    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
        headers=owner,
        json={"groupName": "订单"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "groupName": "订单",
        "newGroupName": "",
        "updatedCount": 2,
    }

    assert _detail(api, owner, first)["tags"] == []
    assert _detail(api, owner, first)["version"] == 2
    assert _detail(api, owner, second)["tags"] == []
    assert _detail(api, owner, second)["version"] == 2
    assert _detail(api, owner, other)["tags"] == ["账户"]

    again = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
        headers=owner,
        json={"groupName": "订单"},
    )
    assert again.status_code == 404
    assert again.json()["code"] == 3818


def test_move_interface_to_group_puts_target_first_and_can_clear_tags(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    interface_id = make_interface(
        api,
        owner,
        software_repository_id,
        tags=["订单", "查询"],
    )

    moved = api.patch(
        f"/v1/api-interfaces/{interface_id}/group",
        headers=owner,
        json={"groupName": "账户"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["tags"] == ["账户", "订单", "查询"]
    assert moved.json()["data"]["version"] == 2

    # 省略 groupName 是无效请求，不能被解释为「清空全部标签」。
    omitted = api.patch(
        f"/v1/api-interfaces/{interface_id}/group",
        headers=owner,
        json={},
    )
    assert omitted.status_code == 400
    assert _detail(api, owner, interface_id)["tags"] == ["账户", "订单", "查询"]

    cleared = api.patch(
        f"/v1/api-interfaces/{interface_id}/group",
        headers=owner,
        json={"groupName": ""},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["tags"] == []
    assert cleared.json()["data"]["version"] == 3

    reserved = api.patch(
        f"/v1/api-interfaces/{interface_id}/group",
        headers=owner,
        json={"groupName": "未分类"},
    )
    assert reserved.status_code == 400
    assert reserved.json()["message"] == "分组名称不能为「未分类」"

    reserved_tag = api.patch(
        f"/v1/api-interfaces/{interface_id}",
        headers=owner,
        json={"tags": ["未分类"]},
    )
    assert reserved_tag.status_code == 400
    assert reserved_tag.json()["message"] == "标签不能为「未分类」"


def test_group_operations_require_write_access(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, developer = account(api, "developer")
    pid = project(api, owner)
    add_member(api, owner, pid, "viewer", "viewer")
    add_member(api, owner, pid, "developer", "developer")
    software_repository_id = make_software_repository(api, owner, pid)
    interface_id = make_interface(
        api,
        owner,
        software_repository_id,
        tags=["订单"],
    )

    rename_payload = {"currentGroupName": "订单", "newGroupName": "订单管理"}
    for headers in (viewer, developer):
        assert (
            api.post(
                f"/v1/software-repositories/{software_repository_id}/interface-groups",
                headers=headers,
                json={"groupName": "新分组"},
            ).status_code
            == 403
        )
        assert (
            api.post(
                f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
                headers=headers,
                json=rename_payload,
            ).status_code
            == 403
        )
        assert (
            api.post(
                f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
                headers=headers,
                json={"groupName": "订单"},
            ).status_code
            == 403
        )
        assert (
            api.patch(
                f"/v1/api-interfaces/{interface_id}/group",
                headers=headers,
                json={"groupName": "账户"},
            ).status_code
            == 403
        )


def test_created_group_persists_without_interfaces_and_can_be_renamed_deleted(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)

    created = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups",
        headers=owner,
        json={"groupName": " 空分组 "},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"] == {
        "groupName": "空分组",
        "newGroupName": "空分组",
        "updatedCount": 0,
    }
    repository = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]
    assert repository["interfaceGroups"] == ["空分组"]

    listed = api.get(f"/v1/projects/{pid}/software-repositories", headers=owner).json()["data"]
    assert listed["items"][0]["interfaceGroups"] == ["空分组"]

    duplicate = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups",
        headers=owner,
        json={"groupName": "空分组"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 3819

    interface_id = make_interface(api, owner, software_repository_id, tags=["空分组"])
    derived_conflict = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups",
        headers=owner,
        json={"groupName": "空分组"},
    )
    assert derived_conflict.status_code == 409
    assert derived_conflict.json()["code"] == 3819

    renamed = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "空分组", "newGroupName": "新分组"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["updatedCount"] == 1
    repository = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]
    assert repository["interfaceGroups"] == ["新分组"]
    assert _detail(api, owner, interface_id)["tags"] == ["新分组"]

    deleted = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
        headers=owner,
        json={"groupName": "新分组"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["updatedCount"] == 1
    repository = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]
    assert repository["interfaceGroups"] == []
    assert _detail(api, owner, interface_id)["tags"] == []

    missing = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
        headers=owner,
        json={"groupName": "新分组"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 3818


def test_empty_created_group_can_be_renamed_and_deleted(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups",
        headers=owner,
        json={"groupName": "空分组"},
    )

    renamed = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/rename",
        headers=owner,
        json={"currentGroupName": "空分组", "newGroupName": "另一个空分组"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["updatedCount"] == 0
    repository = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]
    assert repository["interfaceGroups"] == ["另一个空分组"]

    deleted = api.post(
        f"/v1/software-repositories/{software_repository_id}/interface-groups/delete",
        headers=owner,
        json={"groupName": "另一个空分组"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["updatedCount"] == 0
    repository = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]
    assert repository["interfaceGroups"] == []
