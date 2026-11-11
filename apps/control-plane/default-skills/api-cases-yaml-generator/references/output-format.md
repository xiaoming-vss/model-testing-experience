# Output Format Reference

Use this as the compact canonical example for YAML output.

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

Notes:

- output must be a YAML object with a top-level `cases:` key
- every case must include `orderNo`
- `orderNo` must be an integer and the final `cases:` list must be sorted by ascending `orderNo`
- use `urlTemplate`, not `url`
- use `headers`, `query`, `bodyType`, and `bodyJson` directly on each case
- use `extractRules` and `assertRules`, not `extract` or `validate`
- preserve template expressions like `{{token}}` and `{{$uuid}}`
- emit pure YAML only when the user asks for direct conversion output
