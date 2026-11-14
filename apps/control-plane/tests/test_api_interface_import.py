"""OpenAPI import preview, diff, commit and base path rules."""

import json

from support.api_assets import (
    add_member,
    make_app,
    make_interface,
    openapi_document,
    upload_commit,
    upload_preview,
)
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project
from support.project_api import api as api


def _interface_by_path(api, headers, project_id, path):
    data = api.get(
        f"/v1/projects/{project_id}/api-interfaces?keyword={path}", headers=headers
    ).json()["data"]
    return next(item for item in data["items"] if item["path"] == path)


def test_preview_and_commit_new_then_unchanged_then_modified(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint, "收银台重构")
    app_id = make_app(api, owner, pid, basePath="/api/v2")
    document = openapi_document()
    document["paths"]["/orders/{orderId}"] = {
        "get": {
            "summary": "订单详情",
            "responses": {"200": {"description": "成功"}},
        }
    }

    preview = upload_preview(api, owner, app_id, document)
    assert preview["summary"] == {
        "new": 2,
        "modified": 0,
        "unchanged": 0,
        "libraryOnly": 0,
    }
    assert preview["source"]["digest"]
    assert preview["source"]["basePath"] == "/api/v2"
    assert preview["basePathChange"] is None
    new_items = [item for item in preview["items"] if item["changeType"] == "new"]
    assert {item["key"] for item in new_items} == {"POST /orders", "GET /orders/{orderId}"}

    result = upload_commit(
        api,
        owner,
        app_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=[item["key"] for item in new_items],
    )
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["appBasePath"] == "/api/v2"

    order = _interface_by_path(api, owner, pid, "/orders")
    detail = api.get(f"/v1/api-interfaces/{order['interfaceId']}", headers=owner).json()["data"]
    assert detail["name"] == "创建订单"
    assert detail["source"]["type"] == "openapi_file"
    assert detail["source"]["name"] == "Order API"
    assert detail["source"]["version"] == "2.0"
    assert detail["source"]["importedAt"]
    assert any(header["name"] == "Content-Type" for header in detail["headers"])

    # Save library-only state that must survive the next import.
    api.patch(
        f"/v1/api-interfaces/{order['interfaceId']}",
        headers=owner,
        json={"enabled": False, "requirementIds": [requirement_id]},
    )
    make_interface(
        api,
        owner,
        app_id,
        name="旧接口",
        method="GET",
        path="/legacy",
    )

    unchanged = upload_preview(api, owner, app_id, document)
    assert unchanged["summary"] == {
        "new": 0,
        "modified": 0,
        "unchanged": 2,
        "libraryOnly": 1,
    }
    library = next(item for item in unchanged["items"] if item["changeType"] == "library_only")
    assert library["path"] == "/legacy"

    document["paths"]["/orders"]["post"]["summary"] = "创建订单 V2"
    document["paths"]["/orders"]["post"]["responses"]["200"]["description"] = "创建成功"
    modified = upload_preview(api, owner, app_id, document)
    changed = next(item for item in modified["items"] if item["changeType"] == "modified")
    assert changed["key"] == "POST /orders"
    assert set(changed["changedFields"]) == {"name", "responseDescription"}

    result = upload_commit(
        api,
        owner,
        app_id,
        document,
        digest=modified["source"]["digest"],
        selected_keys=[changed["key"]],
        expected_items={changed["key"]: changed["existingVersion"]},
    )
    assert result["created"] == 0
    assert result["updated"] == 1
    assert result["libraryOnly"] == 1

    detail = api.get(f"/v1/api-interfaces/{order['interfaceId']}", headers=owner).json()["data"]
    assert detail["name"] == "创建订单 V2"
    assert detail["responseDescription"] == "创建成功"
    assert detail["enabled"] is False
    assert detail["requirements"][0]["requirementId"] == requirement_id
    legacy = _interface_by_path(api, owner, pid, "/legacy")
    assert api.get(f"/v1/api-interfaces/{legacy['interfaceId']}", headers=owner).status_code == 200


def test_import_requires_expected_version_for_existing(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    document = openapi_document()

    preview = upload_preview(api, owner, app_id, document)
    upload_commit(
        api,
        owner,
        app_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=["POST /orders"],
    )
    document["paths"]["/orders"]["post"]["summary"] = "改名"
    modified = upload_preview(api, owner, app_id, document)
    item = next(item for item in modified["items"] if item["changeType"] == "modified")

    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import",
        headers=owner,
        data={
            "sourceDigest": modified["source"]["digest"],
            "selectedKeys": json.dumps([item["key"]]),
            "expectedItems": "{}",
        },
        files={"file": ("openapi.json", json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3809


def test_source_digest_mismatch_is_rejected(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    document = openapi_document()
    upload_preview(api, owner, app_id, document)
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import",
        headers=owner,
        data={
            "sourceDigest": "wrong",
            "selectedKeys": json.dumps(["POST /orders"]),
            "expectedItems": "{}",
        },
        files={"file": ("openapi.json", json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3808


def test_base_path_change_is_owner_only_and_applied_atomically(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    add_member(api, owner, pid, "member", "member")
    app_id = make_app(api, owner, pid, basePath="/api/v1")
    document = openapi_document()
    document["servers"] = [{"url": "https://api.example.com/api/v2"}]

    member_preview = upload_preview(api, member, app_id, document)
    assert member_preview["basePathChange"] == {
        "current": "/api/v1",
        "document": "/api/v2",
        "canApply": False,
    }
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import",
        headers=member,
        data={
            "sourceDigest": member_preview["source"]["digest"],
            "selectedKeys": json.dumps(["POST /orders"]),
        },
        files={"file": ("openapi.json", json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3812

    owner_preview = upload_preview(api, owner, app_id, document)
    app_version = api.get(f"/v1/api-apps/{app_id}", headers=owner).json()["data"]["version"]
    result = upload_commit(
        api,
        owner,
        app_id,
        document,
        digest=owner_preview["source"]["digest"],
        selected_keys=["POST /orders"],
        apply_base_path=True,
        expected_app_version=app_version,
    )
    assert result["appBasePath"] == "/api/v2"
    app = api.get(f"/v1/api-apps/{app_id}", headers=owner).json()["data"]
    assert app["basePath"] == "/api/v2"
    assert app["version"] == app_version + 1


def test_file_required_and_empty_document(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)

    response = api.post(f"/v1/api-apps/{app_id}/interfaces/import/preview", headers=owner)
    assert response.status_code == 400
    assert response.json()["code"] == 3807

    empty = {"openapi": "3.0.1", "info": {}, "paths": {}}
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import/preview",
        headers=owner,
        files={"file": ("openapi.json", json.dumps(empty).encode(), "application/json")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3806


def test_yaml_upload_is_parsed(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    document = """openapi: 3.0.1
info:
  title: YAML API
  version: "1.0"
paths:
  /health:
    get:
      summary: 健康检查
      responses:
        "200":
          description: ok
"""
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import/preview",
        headers=owner,
        files={"file": ("openapi.yaml", document.encode(), "application/yaml")},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"]["name"] == "YAML API"
    assert data["items"][0]["key"] == "GET /health"


def test_library_only_item_cannot_be_selected(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    app_id = make_app(api, owner, pid)
    make_interface(api, owner, app_id, method="GET", path="/legacy")
    document = openapi_document()
    preview = upload_preview(api, owner, app_id, document)
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import",
        headers=owner,
        data={
            "sourceDigest": preview["source"]["digest"],
            "selectedKeys": json.dumps(["GET /legacy"]),
            "expectedItems": json.dumps({"GET /legacy": 1}),
        },
        files={"file": ("openapi.json", json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3806
