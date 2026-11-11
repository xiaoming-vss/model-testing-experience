---
name: api-cases-yaml-generator
description: Convert a custom API test configuration dictionary in JSON into importable YAML under a top-level `cases:` key. Use when the user provides API config JSON and wants case-based API test YAML with `name`, `method`, `urlTemplate`, `headers`, `query`, `bodyType`, `bodyJson`, `extractRules`, and `assertRules`, especially when the target platform expects this exact collection-style schema instead of keyword-driven YAML.
---

# API Cases YAML Generator

Use this skill when the user provides a custom API test configuration dictionary in JSON and wants YAML in the `cases:` import format.

For the exact YAML shape and a compact example, see [references/output-format.md](C:\Users\limin\Documents\Codex\2026-05-19\skill-api-skill\api-cases-yaml-generator\references\output-format.md).

## Goal

Convert the input API config JSON into a YAML object with a top-level `cases:` array.

Each target API should generate at least one positive, full-parameter case unless the user explicitly asks for a different scope.

## Input Expectations

The user may provide:

- the full API config JSON
- one or more selected APIs from that JSON
- instructions to generate all APIs or only a subset
- extra requirements about variable naming, assertions, or extraction behavior

If the user specifies target APIs, process only those APIs. Otherwise, process every API entry in the input config.

## Required Output Shape

Return a YAML object with this outer shape:

```yaml
cases:
  - name: Example
```

When the user asks for direct conversion output, return pure YAML only. Do not wrap it in prose or code fences unless the user explicitly asks for explanation or markdown formatting.

## Workflow

1. Read each target API entry from the config JSON.
2. Determine the case execution order from the user-provided API order or, when absent, from the source config order.
3. Build one positive full-parameter case for each target API.
4. Assign `orderNo` to every case as an integer starting from `1` and increasing by `1` in execution order.
5. Map method, path, headers, query, and request body into the target case schema.
6. Generate legal positive mock values from field types and constraints when example values are absent.
7. Scan response definitions for extraction markers or clearly chainable fields and generate `extractRules` when warranted.
8. Generate `assertRules` only when the assertion target is reliable from the config or the user explicitly requests stronger defaults.
9. Sort emitted `cases` by ascending `orderNo` before returning the YAML.
10. Return the final YAML object only.

## Core Rules

### 1. Top-Level Structure

The output must be a YAML object, not a YAML list.

Always use:

```yaml
cases:
  - ...
```

Each case should use only fields supported by this target schema.

### 2. Case Base Fields

Each case must contain:

- `name`
- `orderNo`
- `method`
- `urlTemplate`

Each case may also contain:

- optional `description`
- optional `enabled`
- optional `headers`
- optional `query`
- optional `bodyType`
- optional `bodyJson`
- optional `timeoutMs`
- optional `continueOnFailure`
- optional `extractRules`
- optional `assertRules`

`orderNo` is required on every case, must be an integer, and must not be quoted as a string.

Do not emit unrelated wrapper sections such as `request`, `extract`, or `validate`.

### 3. Naming Guidance

Case names should be readable and stable.

Preferred form:

```text
{api_name}
```

If the source has multiple operations with the same visible name, append a short suffix that keeps names unique and natural.

### 4. URL and Template Logic

Set `urlTemplate` to the source path or URL.

Preserve supported template expressions when they are already implied by the source or explicitly requested, including:

- `{{envVar}}`
- `{{$uuid}}`
- `{{$timestamp}}`
- `{{$timestamp_ms}}`
- `{{$now}}`
- `{{$date "2006-01-02"}}`
- `{{$randomInt 1 9}}`
- `{{$randomString 8}}`

Do not convert these templates into literal values.

### 5. Headers and Query Mapping

Map request headers into `headers` and query parameters into `query`.

Rules:

- keep keys as strings
- keep template values in `{{variable}}` form when chaining is intended
- omit `headers` or `query` only when they are truly empty and the user does not want explicit empty objects
- preserve `Authorization: "{{token}}"` style variables when auth depends on a prior extraction

### 6. Request Body Mapping

Map the request body using `bodyType` and the corresponding payload field.

Use:

- `bodyType: json` with `bodyJson` for JSON object payloads
- `bodyType: form` with `bodyJson` for form-like key/value payloads when the target platform expects imported structured fields there
- `bodyType: none` when the request does not send a body, especially common for GET

If the source body is truly raw text and the user did not define a target raw-body field, avoid inventing unsupported fields. Either:

- omit that case when the task is strict conversion, or
- ask for clarification if raw-body support is necessary to complete the requested scope

### 7. Mock Data Generation

Generate valid positive-path mock data from field hints in the config.

Use constraints when present, such as:

- `maxLength`
- `format:email`
- `format:uuid`
- `format:date-time`
- numeric constraints
- enum hints

Generate reasonable valid values. Do not invent business semantics beyond the field name and explicit constraints.

Prefer readable values that are helpful in later assertions or extractions.

### 8. Extract Rule Generation

Generate `extractRules` only when there is a reliable extraction target.

Typical triggers:

- response fields marked with `# [关键提取]`
- explicit user instruction to extract a field
- obvious chaining fields such as token, id, name, or status that the user clearly wants reused

Each extract rule should contain:

- `name`
- optional `enabled`
- optional `orderNo`
- `source`
- optional `sourceExpr`
- `varKey`
- optional `defaultValue`

Preferred source mapping:

- response header -> `source: header`
- response JSON field -> `source: body_jsonpath`
- response text regex -> `source: body_text`
- HTTP status code -> `source: status_code`

For `body_jsonpath`, use JSONPath in `sourceExpr`, for example:

```text
$.data.accessToken
```

When extraction is not required, omit `extractRules` or return `[]` only if the user explicitly wants empty arrays preserved.

### 9. Assert Rule Generation

Generate `assertRules` conservatively.

Only add assertions that are supported by the input config or clearly requested by the user. Prefer no assertion over a fabricated one.

Each assert rule should contain:

- `name`
- optional `enabled`
- optional `orderNo`
- `assertSource`
- optional `targetExpr`
- `comparator`
- optional `expectedValue`

Preferred comparators:

- `eq`
- `neq`
- `contains`
- `not_contains`
- `gt`
- `gte`
- `lt`
- `lte`
- `exists`
- `regex`

Recommended default behavior:

- include a `status_code eq 200` assertion when the source or user intent clearly expects a normal success response
- include 0 to 2 business assertions when the expected field and expected value are obvious from the config
- return `assertRules: []` when the source does not support reliable assertions and the user expects schema completeness

### 10. Ordering and Optional Fields

`orderNo` is required on every case.

Case ordering rules:

- emit `orderNo` as an integer such as `1`, `2`, `3`
- assign `orderNo` in actual execution order
- preserve explicit source order when the source already defines one
- otherwise use the input API appearance order
- sort the final `cases` array by ascending `orderNo`

When `extractRules` or `assertRules` contain multiple items, prefer integer `orderNo` values there as well and keep them in ascending order.

For optional booleans:

- default `enabled` to `true` when included
- default `continueOnFailure` to `false` unless the user or source says otherwise

For timeout:

- use `timeoutMs` when the source provides a timeout
- otherwise prefer `5000` only when the user expects explicit defaults in the YAML

### 11. Output Cleanliness

When the user requests direct YAML generation:

- output pure YAML only
- do not add explanation
- do not add markdown fences
- do not add introductory or closing text

## Behavioral Constraints

- Do not output keyword-driven sections like `request`, `extract`, or `validate`.
- Do not convert `{{variable}}` templates into hard-coded values.
- Do not invent unsupported target fields beyond the schema the user provided.
- Do not generate negative cases unless the user explicitly asks for them.
- Do not omit APIs that the user explicitly asked to convert.

## Reference Loading

Only read extra references when needed:

- Read [references/output-format.md](C:\Users\limin\Documents\Codex\2026-05-19\skill-api-skill\api-cases-yaml-generator\references\output-format.md) when you need to verify the final YAML shape or show a canonical compact example.

## Final Check Before Responding

Before returning the result, verify:

- output is a YAML object with a top-level `cases:` key
- each target API has at least one positive case unless the user requested otherwise
- every case contains `orderNo`
- every case `orderNo` is an integer, not a quoted string
- the final `cases` array is sorted by ascending `orderNo`
- request method and URL are mapped correctly
- `bodyType` and `bodyJson` match the source request style
- `extractRules` use the correct `source` and expression type
- `assertRules` contain only reliable assertions
- no explanatory prose leaked into pure YAML output
