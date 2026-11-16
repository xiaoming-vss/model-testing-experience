# 输出格式

目标 API 测试配置字典的紧凑规范示例：

```json
{
  "api_name_in_snake_case": {
    "path": "/api/xxx/{dynamic_id}",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json # [必传]",
      "Authorization": "Bearer {{access_token}} # [必传]"
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

说明：

- 顶层键必须是 snake_case 接口名称。
- 使用 `json` 表示 JSON 请求体，使用 `data` 表示表单请求体。
- 顶层响应是数组时，`response` 直接使用数组。
- 不增加 `items`、`list`、`data` 等包装键。
- 认证占位符使用 `{{access_token}}`、`{{basic_credentials}}` 等双花括号形式。
- 调用方要求纯转换时只返回 JSON 对象，不附解释或 Markdown 代码块。
