# 输入契约

输入是 JSON 对象，包含本批接口提取子集和需求上下文：

```json
{
  "apiExtraction": {
    "create_user": {
      "path": "/api/users",
      "method": "POST",
      "headers": {
        "Authorization": "Bearer {{access_token}} # [必传]"
      },
      "json": {
        "name": "string (必传, maxLength:20) # 用户名",
        "age": "integer (可选, minimum:18) # 年龄"
      },
      "response": {
        "id": "string (format:uuid) # [关键提取] 用户 ID"
      }
    }
  },
  "requirement": {
    "requirementId": "req-1",
    "name": "用户管理",
    "instruction": "重点覆盖创建用户的参数校验"
  },
  "batch": {
    "index": 1,
    "total": 2,
    "interfaceNames": ["create_user"]
  }
}
```

## 字段说明

- `apiExtraction`：本批接口的提取产物。字段值中的 `必传`、`minimum:18`、`maxLength:20`、`enum:admin,user`、`format:email` 等文本就是设计依据的原文。
- `requirement`：需求上下文。`instruction` 是调用方的生成要求，只影响取舍和优先级，不能作为接口事实来源。
- `batch`：本批只设计 `interfaceNames` 列出的接口，输出不得多、不得少。
- 继续优化时额外包含 `currentDesign` 和 `revisionInstruction`。`currentDesign.interfaces` 只包含本批接口的当前设计。

## 依据边界

- 只使用 `apiExtraction` 中出现的接口、字段、类型、必传标记和约束。
- 不读取或推测接口 description、tags、源码、仓库或 OpenAPI 原文。
- 提取产物没有声明的约束、错误码和响应字段不能出现在设计中。
