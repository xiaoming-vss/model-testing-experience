"""OpenAPI import preview, diff, commit and base path rules."""

import json

from support.api_assets import (
    add_member,
    make_interface,
    make_software_repository,
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
    software_repository_id = make_software_repository(api, owner, pid, base_path="/api/v2")
    document = openapi_document()
    document["paths"]["/orders/{orderId}"] = {
        "get": {
            "summary": "订单详情",
            "responses": {"200": {"description": "成功"}},
        }
    }

    preview = upload_preview(api, owner, software_repository_id, document)
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
    new_by_key = {item["key"]: item for item in new_items}
    assert new_by_key["POST /orders"]["tags"] == ["订单"]
    assert new_by_key["POST /orders"]["existingTags"] == []
    assert new_by_key["GET /orders/{orderId}"]["tags"] == []
    assert new_by_key["GET /orders/{orderId}"]["existingTags"] == []

    result = upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=[item["key"] for item in new_items],
    )
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert result["softwareRepositoryBasePath"] == "/api/v2"

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
        json={"requirementIds": [requirement_id]},
    )
    make_interface(
        api,
        owner,
        software_repository_id,
        name="旧接口",
        method="GET",
        path="/legacy",
    )

    unchanged = upload_preview(api, owner, software_repository_id, document)
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
    modified = upload_preview(api, owner, software_repository_id, document)
    changed = next(item for item in modified["items"] if item["changeType"] == "modified")
    assert changed["key"] == "POST /orders"
    assert set(changed["changedFields"]) == {"name", "responseDescription"}

    result = upload_commit(
        api,
        owner,
        software_repository_id,
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
    assert detail["requirements"][0]["requirementId"] == requirement_id
    legacy = _interface_by_path(api, owner, pid, "/legacy")
    assert api.get(f"/v1/api-interfaces/{legacy['interfaceId']}", headers=owner).status_code == 200


def test_reimport_preserves_library_tags_and_new_interfaces_use_document_tags(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    document = openapi_document()

    preview = upload_preview(api, owner, software_repository_id, document)
    upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=["POST /orders"],
    )
    order = _interface_by_path(api, owner, pid, "/orders")
    updated = api.patch(
        f"/v1/api-interfaces/{order['interfaceId']}",
        headers=owner,
        json={"tags": ["库内分组", "次要"]},
    )
    assert updated.status_code == 200, updated.text

    # A document-only tag change is not an interface content change and must not
    # overwrite the library-owned group.
    document["paths"]["/orders"]["post"]["tags"] = ["文档分组"]
    tags_only = upload_preview(api, owner, software_repository_id, document)
    item = next(item for item in tags_only["items"] if item["key"] == "POST /orders")
    assert item["changeType"] == "unchanged"
    assert item["tags"] == ["库内分组", "次要"]
    assert item["existingTags"] == ["库内分组", "次要"]
    assert "tags" not in item["changedFields"]

    document["paths"]["/orders"]["post"]["summary"] = "创建订单 V2"
    document["paths"]["/refunds"] = {
        "post": {
            "summary": "退款",
            "tags": ["退款分组"],
            "responses": {"200": {"description": "成功"}},
        }
    }
    mixed = upload_preview(api, owner, software_repository_id, document)
    modified = next(item for item in mixed["items"] if item["key"] == "POST /orders")
    assert modified["changeType"] == "modified"
    assert set(modified["changedFields"]) == {"name"}
    assert modified["tags"] == ["库内分组", "次要"]
    assert modified["existingTags"] == ["库内分组", "次要"]
    created = next(item for item in mixed["items"] if item["key"] == "POST /refunds")
    assert created["changeType"] == "new"
    assert created["tags"] == ["退款分组"]
    assert created["existingTags"] == []

    result = upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=mixed["source"]["digest"],
        selected_keys=[modified["key"], created["key"]],
        expected_items={modified["key"]: modified["existingVersion"]},
    )
    assert result["created"] == 1
    assert result["updated"] == 1

    order_detail = api.get(f"/v1/api-interfaces/{order['interfaceId']}", headers=owner).json()[
        "data"
    ]
    assert order_detail["name"] == "创建订单 V2"
    assert order_detail["tags"] == ["库内分组", "次要"]
    refund = _interface_by_path(api, owner, pid, "/refunds")
    refund_detail = api.get(f"/v1/api-interfaces/{refund['interfaceId']}", headers=owner).json()[
        "data"
    ]
    assert refund_detail["tags"] == ["退款分组"]


def test_commit_stores_derived_examples_and_reimport_refills_a_cleared_one(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    document = openapi_document()
    document["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"] = {
        "schema": {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}},
                "confirmOverwrite": {"type": "boolean", "default": False},
            },
        }
    }
    document["paths"]["/orders"]["post"]["responses"]["200"]["content"]["application/json"] = {
        "schema": {
            "type": "object",
            "properties": {"orderId": {"type": "integer", "minimum": 1}},
        }
    }
    derived = {"items": ["string"], "confirmOverwrite": False}
    derived_response = {"orderId": 1}

    preview = upload_preview(api, owner, software_repository_id, document)
    result = upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=["POST /orders"],
    )
    created = next(item for item in result["interfaces"] if item["key"] == "POST /orders")
    detail = api.get(f"/v1/api-interfaces/{created['interfaceId']}", headers=owner).json()["data"]
    assert detail["bodyExample"] == derived
    assert detail["responseExample"] == derived_response

    # The same document derives the same examples, so they never count as a change on their own.
    assert upload_preview(api, owner, software_repository_id, document)["summary"]["modified"] == 0

    # Interfaces imported before examples were derived have none; the next import fills them in.
    api.patch(
        f"/v1/api-interfaces/{created['interfaceId']}",
        headers=owner,
        json={"bodyExample": None, "responseExample": None},
    )
    cleared = api.get(f"/v1/api-interfaces/{created['interfaceId']}", headers=owner).json()["data"]
    assert cleared["bodyExample"] is None
    assert cleared["responseExample"] is None
    preview = upload_preview(api, owner, software_repository_id, document)
    changed = next(item for item in preview["items"] if item["key"] == "POST /orders")
    assert changed["changeType"] == "modified"
    assert changed["changedFields"] == ["bodyExample", "responseExample"]
    upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=[changed["key"]],
        expected_items={changed["key"]: changed["existingVersion"]},
    )
    detail = api.get(f"/v1/api-interfaces/{created['interfaceId']}", headers=owner).json()["data"]
    assert detail["bodyExample"] == derived
    assert detail["responseExample"] == derived_response


def test_import_requires_expected_version_for_existing(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
    document = openapi_document()

    preview = upload_preview(api, owner, software_repository_id, document)
    upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=preview["source"]["digest"],
        selected_keys=["POST /orders"],
    )
    document["paths"]["/orders"]["post"]["summary"] = "改名"
    modified = upload_preview(api, owner, software_repository_id, document)
    item = next(item for item in modified["items"] if item["changeType"] == "modified")

    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import",
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
    software_repository_id = make_software_repository(api, owner, pid)
    document = openapi_document()
    upload_preview(api, owner, software_repository_id, document)
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import",
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
    software_repository_id = make_software_repository(api, owner, pid, base_path="/api/v1")
    document = openapi_document()
    document["servers"] = [{"url": "https://api.example.com/api/v2"}]

    member_preview = upload_preview(api, member, software_repository_id, document)
    assert member_preview["basePathChange"] == {
        "current": "/api/v1",
        "document": "/api/v2",
        "canApply": False,
    }
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import",
        headers=member,
        data={
            "sourceDigest": member_preview["source"]["digest"],
            "selectedKeys": json.dumps(["POST /orders"]),
        },
        files={"file": ("openapi.json", json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 3812

    owner_preview = upload_preview(api, owner, software_repository_id, document)
    software_repository_version = api.get(
        f"/v1/software-repositories/{software_repository_id}", headers=owner
    ).json()["data"]["version"]
    result = upload_commit(
        api,
        owner,
        software_repository_id,
        document,
        digest=owner_preview["source"]["digest"],
        selected_keys=["POST /orders"],
        apply_base_path=True,
        expected_software_repository_version=software_repository_version,
    )
    assert result["softwareRepositoryBasePath"] == "/api/v2"
    app = api.get(f"/v1/software-repositories/{software_repository_id}", headers=owner).json()[
        "data"
    ]
    assert app["basePath"] == "/api/v2"
    assert app["version"] == software_repository_version + 1


def test_file_required_and_empty_document(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)

    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import/preview",
        headers=owner,
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3807

    empty = {"openapi": "3.0.1", "info": {}, "paths": {}}
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import/preview",
        headers=owner,
        files={"file": ("openapi.json", json.dumps(empty).encode(), "application/json")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 3806


def test_yaml_upload_is_parsed(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    software_repository_id = make_software_repository(api, owner, pid)
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
        f"/v1/software-repositories/{software_repository_id}/interfaces/import/preview",
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
    software_repository_id = make_software_repository(api, owner, pid)
    make_interface(api, owner, software_repository_id, method="GET", path="/legacy")
    document = openapi_document()
    preview = upload_preview(api, owner, software_repository_id, document)
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import",
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
