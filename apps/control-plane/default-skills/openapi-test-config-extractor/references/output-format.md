# Output Format Reference

Use this as the canonical compact example for the target API test configuration dictionary.

```json
{
  "api_name_in_snake_case": {
    "path": "/api/xxx/{dynamic_id}",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json # [必传]",
      "Authorization": "Bearer {access_token} # [必传]"
    },
    "json": {
      "field1": "string (必传, max:50) # 字段描述",
      "field2": "object (可选, 允许任意键值对/any)"
    },
    "response": {
      "id": "string (format:uuid) # [关键提取] 用于后续操作传承",
      "status": "string"
    }
  }
}
```

Notes:

- top-level key must be endpoint name in `snake_case`
- use `json` for JSON body and `data` for form body
- if top-level response is an array, `response` must directly be an array
- do not invent wrapper keys like `items`, `list`, or `data`
