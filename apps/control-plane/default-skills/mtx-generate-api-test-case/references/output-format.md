# 输出格式

YAML 输出的紧凑规范示例：

```yaml
cases:
  - name: 登录
    description: ""
    enabled: true
    orderNo: 1
    method: POST
    urlTemplate: /v1/login
    headers: {}
    query: {}
    bodyType: json
    bodyJson:
      name: "{{name}}"
      password: "{{passwd}}"
    timeoutMs: 5000
    continueOnFailure: true
    extractRules:
      - name: 提取token
        enabled: true
        orderNo: 1
        source: body_jsonpath
        sourceExpr: $.data.accessToken
        varKey: token
        defaultValue: ""
    assertRules:
      - name: 响应码成功
        enabled: true
        orderNo: 1
        assertSource: status_code
        targetExpr: ""
        comparator: eq
        expectedValue: "200"
```

说明：

- 输出必须是带顶层 `cases:` 键的 YAML 对象。
- 每个用例必须包含 `orderNo`。
- `orderNo` 必须是整数，最终 `cases` 按升序排列。
- 使用 `urlTemplate`，不要使用 `url`。
- 直接在用例上使用 `headers`、`query`、`bodyType`、`bodyJson`。
- 使用 `extractRules`、`assertRules`，不要使用 `extract`、`validate`。
- 保留 `{{token}}`、`{{$uuid}}` 等模板表达式。
- 调用方要求直接转换时只输出纯 YAML。
