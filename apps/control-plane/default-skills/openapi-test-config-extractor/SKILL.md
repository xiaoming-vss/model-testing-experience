---
name: openapi-test-config-extractor
description: Convert OpenAPI or Swagger JSON into a custom API test configuration dictionary for automation testing. Use when the user provides OpenAPI/Swagger 2.0 or 3.0 JSON and wants one endpoint or all endpoints transformed into a structured test config with strict field constraints, auth header handling, response key extraction markers, and no invented fields.
---

# OpenAPI Test Config Extractor

Use this skill when the user wants to transform OpenAPI or Swagger JSON into a custom API test configuration dictionary for automated testing.

For the exact target structure and a compact example, see [references/output-format.md](D:\GoProjects\patterns_study\skills\openapi-test-config-extractor\references\output-format.md).

## Goal

Convert the provided OpenAPI or Swagger JSON into a structured configuration object that:

- faithfully preserves source-defined fields and constraints
- does not invent missing parameters, defaults, limits, or business rules
- adds automation-oriented annotations where required
- can be directly consumed by a test framework

## Input Expectations

The user may provide:

- a full OpenAPI or Swagger JSON document
- a subset of the document
- one specific endpoint to extract
- all endpoints to extract

If the user specifies an endpoint, process only that endpoint. Otherwise, process all available endpoints.

## Required Output Shape

Return a JSON object keyed by endpoint name in `snake_case`.

Use `json` for JSON request bodies and `data` for form-like bodies.

## Workflow

If the task is large or repetitive, prefer the bundled script:

- `scripts/extract_openapi_config.py`

1. Identify target endpoints from `paths`.
2. For each endpoint, extract:
   - `path`
   - HTTP `method`
   - request headers
   - path parameters
   - query parameters
   - request body schema
   - success response schema, preferably HTTP 200 when available
3. Resolve schema references as needed from Swagger 2.0 definitions or OpenAPI 3.x components.
4. Convert extracted fields into the custom dictionary format.
5. Apply annotation and constraint rules exactly.
6. Return only the final structured result unless the user explicitly asks for explanation.

## Extraction Rules

### 1. Source Fidelity

- Never fabricate fields, values, defaults, length limits, formats, or business meaning not explicitly present in the source JSON.
- Preserve as many original constraints as possible while fitting the target format.
- Keep output clear and unambiguous.

### 2. Field String Format

Represent extracted parameter fields in this format:

```text
"字段名": "数据类型 (是否必传, 附加约束) # 字段描述"
```

Examples of constraints to preserve when present:

- `maxLength:100`
- `format:email`
- `default:false`
- `minimum`
- `maximum`
- `enum`

If no description exists, omit the trailing description comment rather than inventing one.

### 3. Request Headers and Security

If the endpoint declares `security`, force-add:

```json
"Authorization": "Bearer {access_token} # [必传]"
```

Also extract and preserve `Content-Type` when it is implied or declared by the request body shape.

Guidance:

- JSON body -> use `json`
- form body -> use `data`

### 4. Noise Reduction for Framework-Generated Login Fields

When processing login or authentication endpoints, apply blacklist filtering and discard these four framework-generated OAuth2 or FastAPI boilerplate fields:

- `grant_type`
- `scope`
- `client_id`
- `client_secret`

This filtering is mandatory only for login or authentication endpoints.

At the same time, preserve all other original form fields exactly as defined in the source schema:

- regardless of field name
- regardless of whether required or optional
- without omission
- without renaming
- without changing constraints or descriptions

Only the four blacklist fields above may be dropped under this rule.

### 5. Response Key Marking

For successful response fields that are clearly useful for downstream chaining, append:

```text
# [关键提取] 用于后续操作传承
```

Typical key fields include:

- `id`
- `*_id`
- `access_token`
- `token`

Do not over-mark unrelated fields.

### 6. Array Response Rule

If the top-level response itself is an array, then `response` must directly be a JSON array:

```json
"response": [
  {
    "id": "string # [关键提取] 用于后续操作传承"
  }
]
```

Do not wrap it with invented keys such as:

- `items`
- `list`
- `data`
- `model_item`

### 7. additionalProperties Rule

If a field contains `additionalProperties: true`, represent it as:

```text
"object (允许任意键值对/any)"
```

Do not copy placeholder examples such as `additionalProp1`.

## Schema Conversion Guidance

When converting schema fields:

- `string` -> `string`
- `integer` -> `integer`
- `number` -> `number`
- `boolean` -> `boolean`
- `object` -> `object`
- `array` -> array containing converted item schema

Required status should reflect schema or parameter-level requirement:

- required -> `必传`
- optional -> `可选`

## Endpoint Sections

Build sections only when they exist:

- `headers`
- `path_params`
- `query`
- `json`
- `data`
- `response`

Do not create empty sections just for completeness.

## Reference Loading

Only read extra references when needed:

- Read [references/output-format.md](D:\GoProjects\patterns_study\skills\openapi-test-config-extractor\references\output-format.md) when you need to verify final output structure or show the user a compact canonical example.

## Script Usage

For larger specs, prefer running:

```bash
python scripts/extract_openapi_config.py --input /path/to/openapi.json
```

Useful filters:

```bash
python scripts/extract_openapi_config.py --input /path/to/openapi.json --keyword login --keyword register
python scripts/extract_openapi_config.py --input /path/to/openapi.json --endpoint POST:/auth/login
```

## Behavioral Constraints

- Do not simplify away important constraints.
- Do not infer undocumented auth schemes beyond the explicit `security` rule above.
- Do not mix response wrappers with the direct top-level schema shape.
- Do not output explanatory prose if the user asked for pure conversion.

## Preferred Working Style

When transforming:

1. inspect endpoint-level parameters first
2. merge schema-derived body fields carefully
3. inspect success response schema
4. mark downstream-valuable fields
5. verify no invented content slipped in

## Final Check Before Responding

Before returning the result, verify:

- all fields come from the source
- all available constraints are preserved
- auth header was added when `security` exists
- array responses are not wrapped
- `additionalProperties` was handled correctly
- key chaining fields are annotated
- output keys are in `snake_case`
