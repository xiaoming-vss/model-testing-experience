"""Shared helpers for interface library API tests; no collected cases."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4


def make_software_repository(
    api,
    headers,
    project_id,
    name="支付网关",
    *,
    base_path="",
    description="",
    software_repository_id=None,
):
    """Seed a software repository directly; interface tests do not exercise GitLab lookup."""

    from testing_agent.models.software_repository import SoftwareRepository

    repository_id = software_repository_id or f"software-repository-{uuid4().hex[:12]}"

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add(
                SoftwareRepository(
                    software_repository_id=repository_id,
                    project_id=project_id,
                    name=name,
                    description=description,
                    base_path=base_path,
                    repository_project_id=f"gitlab-project-{repository_id}",
                    repository_group_id="group-1",
                    repository_instance_key="",
                    repository_path=f"commerce/{name}",
                    repository_name=name,
                    repository_instance_url="https://gitlab.example.com",
                    version=1,
                    created_by_user_id="test-owner",
                )
            )
            await session.commit()

    asyncio.run(seed())
    return repository_id


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
        "requirementIds": [],
    }
    body.update(overrides)
    return body


def make_interface(api, headers, software_repository_id, **overrides):
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces",
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


def upload_preview(api, headers, software_repository_id, document, filename="openapi.json"):
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import/preview",
        headers=headers,
        files={"file": (filename, json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upload_commit(
    api,
    headers,
    software_repository_id,
    document,
    *,
    digest,
    selected_keys,
    expected_items=None,
    apply_base_path=False,
    expected_software_repository_version=None,
    filename="openapi.json",
):
    data = {
        "sourceDigest": digest,
        "selectedKeys": json.dumps(selected_keys),
        "expectedItems": json.dumps(expected_items or {}),
        "applyBasePath": "true" if apply_base_path else "false",
    }
    if expected_software_repository_version is not None:
        data["expectedSoftwareRepositoryVersion"] = str(expected_software_repository_version)
    response = api.post(
        f"/v1/software-repositories/{software_repository_id}/interfaces/import",
        headers=headers,
        data=data,
        files={"file": (filename, json.dumps(document).encode(), "application/json")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]
