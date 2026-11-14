"""Pure OpenAPI 3 / Swagger 2 parsing and mapping tests."""

import pytest

from testing_agent.domain.openapi_import import parse_openapi_document


def test_openapi3_maps_refs_parameters_body_and_response():
    document = {
        "openapi": "3.0.1",
        "info": {"title": "Order API", "version": "2.3.1"},
        "servers": [{"url": "https://api.example.com/api/v2/"}],
        "paths": {
            "/orders/{orderId}": {
                "parameters": [
                    {"$ref": "#/components/parameters/OrderId"},
                    {
                        "name": "X-Trace",
                        "in": "header",
                        "schema": {"type": "string"},
                        "example": "trace-1",
                        "description": "追踪号",
                    },
                ],
                "get": {
                    "summary": "订单详情",
                    "description": "查询订单",
                    "tags": ["订单", "查询"],
                    "parameters": [
                        {
                            "name": "include",
                            "in": "query",
                            "schema": {"type": "array", "items": {"type": "string"}},
                            "example": ["items"],
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "成功",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"},
                                    "example": {"orderId": "o-1"},
                                }
                            },
                        },
                        "404": {"description": "不存在"},
                    },
                },
            },
            "/orders": {
                "post": {
                    "summary": "创建订单",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateOrder"},
                                "example": {"items": []},
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "创建成功",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "parameters": {
                "OrderId": {
                    "name": "orderId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            },
            "schemas": {
                "Order": {
                    "type": "object",
                    "properties": {"orderId": {"type": "string"}},
                },
                "CreateOrder": {
                    "type": "object",
                    "properties": {"items": {"type": "array"}},
                },
            },
        },
    }

    parsed = parse_openapi_document(document, fallback_name="order.json")
    assert parsed.source_name == "Order API"
    assert parsed.source_version == "2.3.1"
    assert parsed.base_path == "/api/v2"
    assert parsed.warnings == []
    assert [endpoint.method for endpoint in parsed.endpoints] == ["POST", "GET"]

    detail = next(endpoint for endpoint in parsed.endpoints if endpoint.method == "GET")
    assert detail.path == "/orders/{orderId}"
    assert detail.name == "订单详情"
    assert detail.description == "查询订单"
    assert detail.tags == ["订单", "查询"]
    assert detail.path_params == [
        {
            "enabled": True,
            "name": "orderId",
            "type": "string",
            "required": True,
            "example": "",
            "description": "",
        }
    ]
    assert detail.query_params[0]["name"] == "include"
    assert detail.query_params[0]["type"] == "array"
    assert detail.headers[0]["name"] == "X-Trace"
    assert detail.body_type == "none"
    assert detail.response_status == 200
    assert detail.response_schema == {
        "type": "object",
        "properties": {"orderId": {"type": "string"}},
    }
    assert detail.response_example == {"orderId": "o-1"}

    create = next(endpoint for endpoint in parsed.endpoints if endpoint.method == "POST")
    assert create.body_type == "json"
    assert create.body_schema == {
        "type": "object",
        "properties": {"items": {"type": "array"}},
    }
    assert create.body_example == {"items": []}
    assert create.response_status == 201
    assert any(
        header["name"] == "Content-Type" and header["example"] == "application/json"
        for header in create.headers
    )


def test_swagger2_maps_base_path_body_and_form_data():
    body_document = {
        "swagger": "2.0",
        "info": {"title": "Legacy", "version": "1.0"},
        "basePath": "/legacy/api",
        "paths": {
            "/users": {
                "post": {
                    "summary": "创建用户",
                    "consumes": ["application/json"],
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}},
                            },
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "成功",
                            "schema": {"type": "object"},
                        }
                    },
                }
            }
        },
    }
    parsed = parse_openapi_document(body_document)
    assert parsed.base_path == "/legacy/api"
    endpoint = parsed.endpoints[0]
    assert endpoint.body_type == "json"
    assert endpoint.body_schema["properties"]["name"]["type"] == "string"
    assert endpoint.response_schema == {"type": "object"}

    form_document = {
        "swagger": "2.0",
        "info": {"title": "Legacy"},
        "paths": {
            "/upload": {
                "post": {
                    "consumes": ["multipart/form-data"],
                    "parameters": [
                        {
                            "name": "file",
                            "in": "formData",
                            "type": "file",
                            "required": True,
                        },
                        {
                            "name": "note",
                            "in": "formData",
                            "type": "string",
                            "example": "hello",
                        },
                    ],
                    "responses": {"200": {"description": "成功"}},
                }
            }
        },
    }
    endpoint = parse_openapi_document(form_document).endpoints[0]
    assert endpoint.body_type == "form"
    assert endpoint.body_schema["properties"]["file"]["type"] == "file"
    assert endpoint.body_schema["required"] == ["file"]
    assert endpoint.body_example == {"note": "hello"}


def test_parser_records_non_blocking_warnings():
    document = {
        "openapi": "3.0.1",
        "info": {"title": "Warnings"},
        "servers": [{"url": "https://api.example.com/{version}"}],
        "paths": {
            "/items": {
                "parameters": [{"name": "session", "in": "cookie", "schema": {"type": "string"}}],
                "get": {
                    "deprecated": True,
                    "security": [{"bearer": []}],
                    "parameters": [
                        {
                            "name": "external",
                            "in": "query",
                            "$ref": "https://example.com/parameter.json",
                        }
                    ],
                    "responses": {"200": {"description": "成功"}},
                },
                "trace": {
                    "responses": {"200": {"description": "成功"}},
                },
            },
        },
    }
    parsed = parse_openapi_document(document)
    codes = {warning["code"] for warning in parsed.warnings}
    assert parsed.base_path == ""
    assert "base_path_variable" in codes
    assert "cookie_parameter_skipped" in codes
    assert "deprecated" in codes
    assert "security_not_imported" in codes
    assert "parameter_ref_unresolved" in codes


def test_parser_skips_duplicate_identity_and_unsupported_methods():
    document = {
        "openapi": "3.0.1",
        "info": {"title": "Duplicate"},
        "paths": {
            "/items/": {"get": {"summary": "第一个", "responses": {"200": {"description": "ok"}}}},
            "/items": {"get": {"summary": "第二个", "responses": {"200": {"description": "ok"}}}},
            "/trace": {"trace": {"responses": {"200": {"description": "ok"}}}},
        },
    }
    parsed = parse_openapi_document(document)
    assert [(endpoint.path, endpoint.name) for endpoint in parsed.endpoints] == [
        ("/items", "第一个")
    ]
    codes = {warning["code"] for warning in parsed.warnings}
    assert "duplicate_identity" in codes


def test_parser_truncates_fields_to_database_limits():
    long_text = "x" * 300
    document = {
        "openapi": "3.0.1",
        "info": {"title": "t" * 300, "version": "v" * 100},
        "paths": {
            "/items": {
                "post": {
                    "summary": "create",
                    "description": "d" * 2000,
                    "requestBody": {
                        "content": {
                            "text/plain": {
                                "example": long_text * 100,
                            }
                        }
                    },
                    "responses": {"200": {"description": "r" * 1000}},
                }
            }
        },
    }
    parsed = parse_openapi_document(document)

    assert len(parsed.source_name) == 255
    assert len(parsed.source_version) == 64
    endpoint = parsed.endpoints[0]
    assert len(endpoint.description) == 1024
    assert len(endpoint.body_text) == 20000
    assert len(endpoint.response_description) == 512
    assert "field_truncated" in {warning["code"] for warning in parsed.warnings}


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"openapi": "3.0.1"},
        {"openapi": "3.0.1", "paths": []},
        {"swagger": "1.2", "paths": {}},
    ],
)
def test_invalid_documents_raise_value_error(document):
    with pytest.raises(ValueError):
        parse_openapi_document(document)
