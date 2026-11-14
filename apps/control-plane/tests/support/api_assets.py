"""Shared helpers for interface library API tests; no collected cases."""

from __future__ import annotations

import json
from typing import Any


def make_app(api, headers, project_id, name="支付网关", **overrides):
    body = {"name": name, **overrides}
    response = api.post(f"/v1/projects/{project_id}/api-apps", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]["appId"]


def interface_body(**overrides) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "创建订单",
        "method": "POST",
        "path": "/orders",
        "description": "创建订单",
        "tags": ["订单"],
        "headers": [
            {
                "enabled": True,
                "name": "Authorization",
                "type": "string",
                "required": True,
                "example": "Bearer token",
                "description": "访问令牌",
            }
        ],
        "pathParams": [],
        "queryParams": [],
        "bodyType": "json",
        "bodySchema": {"type": "object"},
        "bodyExample": {"items": []},
        "bodyText": "",
        "responseStatus": 200,
        "responseDescription": "成功",
        "responseSchema": {"type": "object"},
        "responseExample": {"orderId": "1"},
        "enabled": True,
        "requirementIds": [],
    }
    body.update(overrides)
    return body


def make_interface(api, headers, app_id, **overrides):
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces",
        headers=headers,
        json=interface_body(**overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["interfaceId"]


def add_member(api, owner, project_id, name, role):
    response = api.post(
        f"/v1/projects/{project_id}/members",
        headers=owner,
        json={"name": name, "role": role},
    )
    assert response.status_code == 200, response.text


def openapi_document(**overrides) -> dict[str, Any]:
    document: dict[str, Any] = {
        "openapi": "3.0.1",
        "info": {"title": "Order API", "version": "2.0"},
        "servers": [{"url": "https://api.example.com/api/v2"}],
        "paths": {
            "/orders": {
                "post": {
                    "summary": "创建订单",
                    "tags": ["订单"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                                "example": {"items": []},
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "成功",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                    "example": {"orderId": "1"},
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    document.update(overrides)
    return document


def upload_preview(api, headers, app_id, document, filename="openapi.json"):
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import/preview",
        headers=headers,
        files={"file": (filename, json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upload_commit(
    api,
    headers,
    app_id,
    document,
    *,
    digest,
    selected_keys,
    expected_items=None,
    apply_base_path=False,
    expected_app_version=None,
    filename="openapi.json",
):
    data = {
        "sourceDigest": digest,
        "selectedKeys": json.dumps(selected_keys),
        "expectedItems": json.dumps(expected_items or {}),
        "applyBasePath": "true" if apply_base_path else "false",
    }
    if expected_app_version is not None:
        data["expectedAppVersion"] = str(expected_app_version)
    response = api.post(
        f"/v1/api-apps/{app_id}/interfaces/import",
        headers=headers,
        data=data,
        files={"file": (filename, json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]
