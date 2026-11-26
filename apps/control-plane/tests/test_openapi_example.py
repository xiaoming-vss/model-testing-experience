"""Placeholder request examples derived from request body JSON Schemas."""

from datetime import date

from testing_agent.domain.openapi_example import (
    MAX_EXAMPLE_DEPTH,
    MAX_STRING_LENGTH,
    SAMPLE_UUID,
    generate_example,
)


def test_lists_every_field_and_prefers_values_written_in_the_document():
    example = generate_example(
        {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "authMethod": {"type": "string", "default": "local", "enum": ["ldap", "local"]},
                "role": {"type": "string", "enum": [None, "admin", "member"]},
                "sample": {"type": "object", "example": {"a": 1}},
                "alternatives": {"type": "array", "examples": [[2], [1]]},
                "fixed": {"const": 3},
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "enabled": {"type": "boolean"},
                "cleared": {"type": "string", "default": None},
            },
        }
    )

    assert example == {
        "name": "string",
        "authMethod": "local",
        "role": "admin",
        "sample": {"a": 1},
        "alternatives": [2],
        "fixed": 3,
        "count": 1,
        "ratio": 1.5,
        "enabled": False,
        "cleared": None,
    }


def test_placeholders_respect_length_range_and_format():
    example = generate_example(
        {
            "type": "object",
            "properties": {
                "requestId": {"type": "string", "minLength": 8, "maxLength": 64},
                "tight": {"type": "string", "minLength": 8, "maxLength": 10},
                "tightMax": {"type": "string", "minLength": 7, "maxLength": 12},
                "code": {"type": "string", "maxLength": 3},
                "story": {"type": "string", "minLength": 5000},
                "remoteBugId": {"type": "integer", "exclusiveMinimum": 0},
                "page": {"type": "integer", "minimum": 2, "exclusiveMinimum": True},
                "score": {"type": "number", "maximum": 1},
                "step": {"type": "integer", "minimum": 7, "multipleOf": 5},
                "id": {"type": "string", "format": "uuid"},
                "when": {"type": "string", "format": "date-time"},
                "who": {"type": "string", "format": "email"},
            },
        }
    )

    assert example["requestId"] == "string-string"
    assert 8 <= len(example["tight"]) <= 10
    assert 7 <= len(example["tightMax"]) <= 12
    assert example["code"] == "str"
    assert MAX_STRING_LENGTH <= len(example["story"]) < 80
    assert example["remoteBugId"] == 1
    assert example["page"] == 3
    assert example["score"] == 1
    assert example["step"] == 10
    assert example["id"] == SAMPLE_UUID
    assert example["when"] == "2026-11-23T10:00:00Z"
    assert example["who"] == "user@example.com"


def test_nests_arrays_objects_dictionaries_and_nullable_branches():
    example = generate_example(
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "labels": {"type": "object", "additionalProperties": {"type": "integer"}},
                "meta": {"type": "object"},
                "flags": {"type": "array"},
                "requestId": {"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]},
                "coupon": {"type": ["string", "null"], "maxLength": 16},
                "base": {
                    "allOf": [
                        {"type": "object", "properties": {"a": {"type": "string"}}},
                        {"properties": {"b": {"type": "boolean", "default": True}}},
                    ]
                },
                "missing": {"$ref": "#/components/schemas/Unresolved"},
            },
        }
    )

    assert example == {
        "items": [{"sku": "string", "tags": ["string"]}] * 5,
        "labels": {"key": 1},
        "meta": {},
        "flags": [],
        "requestId": SAMPLE_UUID,
        "coupon": "string",
        "base": {"a": "string", "b": True},
    }


def test_schemas_without_a_json_value_yield_no_example():
    assert generate_example(None) is None
    assert generate_example("not a schema") is None
    assert generate_example({"$ref": "#/components/schemas/Node"}) is None
    assert generate_example({"type": "file"}) is None


def test_document_values_that_cannot_be_stored_fall_back_to_a_placeholder():
    # YAML turns unquoted dates and .nan into Python objects that are not JSON.
    assert generate_example({"type": "string", "default": date(2026, 11, 23)}) == "string"
    assert generate_example({"type": "string", "default": float("nan")}) == "string"
    assert generate_example({"type": "string", "default": "2026-11-23"}) == "2026-11-23"


def test_deeply_nested_schemas_stop_at_the_depth_limit():
    schema: dict = {"type": "string"}
    for _ in range(12):
        schema = {"type": "object", "properties": {"next": schema}}

    example = generate_example(schema)
    depth = 0
    while isinstance(example, dict) and "next" in example:
        example = example["next"]
        depth += 1

    assert depth == MAX_EXAMPLE_DEPTH
