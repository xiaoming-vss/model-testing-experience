# 输出格式

只返回一个 JSON 对象，不返回 Markdown、解释或第二个对象：

```json
{
  "schemaVersion": "api_test_design/1.0",
  "interfaces": {
    "create_user": {
      "method": "POST",
      "path": "/api/users",
      "cases": [
        {
          "id": "create_user_positive_full",
          "title": "创建用户-正向-全参数",
          "category": "positive",
          "priority": "P0",
          "intent": "验证完整合法参数创建用户成功",
          "basis": {"kind": "positive", "section": "", "field": "", "constraint": ""},
          "patch": {},
          "expected": {
            "statusClass": "2xx",
            "assertions": [
              {"assertSource": "body_jsonpath", "targetExpr": "$.id", "comparator": "exists", "expectedValue": ""}
            ]
          }
        },
        {
          "id": "create_user_missing_password",
          "title": "创建用户-反向-缺少必填密码",
          "category": "negative",
          "priority": "P1",
          "intent": "验证缺少必填密码时请求被拒绝",
          "basis": {"kind": "required", "section": "json", "field": "/password", "constraint": "required"},
          "patch": {"json": [{"op": "remove", "path": "/password"}]},
          "expected": {"statusClass": "4xx", "assertions": []}
        },
        {
          "id": "create_user_age_below_min",
          "title": "创建用户-边界-年龄低于最小值",
          "category": "boundary",
          "priority": "P1",
          "intent": "验证年龄小于 minimum:18 时请求被拒绝",
          "basis": {"kind": "constraint", "section": "json", "field": "/profile/age", "constraint": "minimum:18"},
          "patch": {"json": [{"op": "add", "path": "/profile/age", "value": 17}]},
          "expected": {"statusClass": "4xx", "assertions": []}
        }
      ],
      "uncovered": [
        {
          "kind": "constraint",
          "section": "json",
          "field": "/profile/roles/0",
          "constraint": "enum:admin,user",
          "reason": "soft_cap"
        }
      ]
    }
  }
}
```

## 用例字段

- `id`：全局唯一，1–100 字符，建议 snake_case。
- `title`：全局唯一（忽略大小写），1–120 字符；生成 YAML 时直接作为 `name`。
- `category`：`positive | negative | boundary`。
- `priority`：`P0 | P1 | P2`。
- `intent`：1–512 字符；生成 YAML 时写入 `description`。
- `basis`：`kind` 为 `positive | required | constraint | type`；`section` 为 `headers | path_params | query | json | data`，`positive` 时 `section/field/constraint` 为空字符串。
- `patch`：可选；键为分区名，值为 JSON Patch 操作数组，只支持 `add/remove/replace`。`remove` 不带 `value`；`json` 和 `data` 不能同时出现。
- `expected.statusClass`：`2xx | 4xx`。
- `expected.assertions`：`status_code` 不允许作为断言来源；`2xx` 最多 2 条，`4xx` 必须为空；`expectedValue` 必须是字符串。

## 未覆盖字段

`uncovered` 每项包含 `kind/section/field/constraint/reason`。`reason` 为 `soft_cap | low_value | duplicate | not_verifiable`。引用必须在提取产物中存在，且不能同时被某条用例覆盖。
