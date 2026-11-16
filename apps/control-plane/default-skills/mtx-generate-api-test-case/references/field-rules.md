# 字段规则

## 1. 顶层结构

输出必须是 YAML 对象，不是 YAML 列表：

```yaml
cases:
  - ...
```

每个用例只使用目标 schema 支持的字段。

## 2. 用例基础字段

每个用例必须包含：

- `name`
- `orderNo`
- `method`
- `urlTemplate`

按需包含：

- `description`
- `enabled`
- `headers`
- `query`
- `bodyType`
- `bodyJson`
- `timeoutMs`
- `continueOnFailure`
- `extractRules`
- `assertRules`

`orderNo` 必填、必须是整数，不能加引号变成字符串。

不输出 `request`、`extract`、`validate` 等无关包装段。

## 3. 命名

用例名称应可读且稳定。首选：

```text
{api_name}
```

同一可见名称存在多个操作时，追加简短后缀保持唯一且自然。

## 4. URL 与模板

`urlTemplate` 使用源路径或 URL。

源中已有或调用方明确要求的模板表达式必须保留，包括：

- `{{envVar}}`
- `{{$uuid}}`
- `{{$timestamp}}`
- `{{$timestamp_ms}}`
- `{{$now}}`
- `{{$date "2006-01-02"}}`
- `{{$randomInt 1 9}}`
- `{{$randomString 8}}`

不得把这些模板转成字面值。

## 5. 请求头与查询参数

请求头映射到 `headers`，查询参数映射到 `query`。

规则：

- 键保持字符串。
- 需要串联时保留 `{{variable}}` 形式的模板值。
- 只有确实为空且调用方不要求显式空对象时，才省略 `headers` 或 `query`。
- 认证依赖前序提取时，保留 `Authorization: "{{token}}"` 这类变量。

## 6. 请求体

使用 `bodyType` 和对应载荷字段映射请求体：

- JSON 对象载荷 → `bodyType: json` 配 `bodyJson`
- 表单式键值载荷 → `bodyType: form` 配 `bodyJson`（目标平台按结构化字段导入）
- 不发送请求体（尤其是 GET）→ `bodyType: none`

源请求体是纯文本且调用方未定义目标 raw-body 字段时，不编造不支持的字段。可以选择：

- 严格转换任务中省略该用例，或
- 完成范围确实需要 raw-body 支持时请求澄清

## 7. Mock 数据

根据配置中的字段提示生成合法正向 mock 数据。

存在约束时使用：

- `maxLength`
- `format:email`
- `format:uuid`
- `format:date-time`
- 数值约束
- `enum` 提示

生成合理合法值；不超出字段名和显式约束虚构业务语义。优先使用便于后续断言或提取的可读值。

## 8. 提取规则

只在存在可靠提取目标时生成 `extractRules`。

典型触发：

- 响应字段标记 `# [关键提取]`
- 调用方明确要求提取某字段
- token、id、name、status 等明显需要复用的串联字段

每条规则包含：

- `name`
- `enabled`（可选）
- `orderNo`（可选）
- `source`
- `sourceExpr`（可选）
- `varKey`
- `defaultValue`（可选）

`source` 映射：

- 响应头 → `header`
- 响应 JSON 字段 → `body_jsonpath`
- 响应文本正则 → `body_text`
- HTTP 状态码 → `status_code`

`body_jsonpath` 使用 JSONPath 写入 `sourceExpr`，例如：

```text
$.data.accessToken
```

不需要提取时省略 `extractRules`；只有调用方明确要求保留空数组时才返回 `[]`。

## 9. 断言规则

保守生成 `assertRules`。只添加输入配置支持或调用方明确要求的断言；没有可靠断言时优先不写。

每条规则包含：

- `name`
- `enabled`（可选）
- `orderNo`（可选）
- `assertSource`
- `targetExpr`（可选）
- `comparator`
- `expectedValue`（可选）

支持的比较符：

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

默认行为：

- 源或调用方意图明确期待正常成功响应时，添加 `status_code eq 200`。
- 期望字段和期望值可从配置明确判断时，添加 0 到 2 条业务断言。
- 源不支持可靠断言且调用方要求 schema 完整时，返回 `assertRules: []`。

## 10. 排序与可选字段

`orderNo` 在每个用例上必填。

排序规则：

- 使用 `1`、`2`、`3` 这样的整数。
- 按实际执行顺序分配。
- 源已定义顺序时保留源顺序。
- 否则按输入接口出现顺序。
- 最终 `cases` 数组按 `orderNo` 升序排序。

`extractRules` 或 `assertRules` 含多条时，尽量使用整数 `orderNo` 并保持升序。

可选布尔值：

- 包含 `enabled` 时默认 `true`。
- 除非源或调用方另有说明，`continueOnFailure` 默认 `false`。

超时：

- 源提供超时时使用 `timeoutMs`。
- 只有调用方要求显式默认值时才优先使用 `5000`。

## 11. 输出纯净

调用方要求直接生成 YAML 时：

- 只输出纯 YAML。
- 不加解释。
- 不加 Markdown 代码块。
- 不加开头或结尾文字。

## 12. 设计驱动模式

输入包含 `apiDesign` 时，以下规则优先于第 4–9 节的默认行为：

- 只生成 `batch.caseIds` 指定的设计用例，一条设计对应一条 YAML，不多不少。
- `name` 等于设计 `title`；`description` 等于设计 `intent`。
- `method` 和 `urlTemplate` 来自 `apiExtraction`；`path_params` 补丁值替换进 URL 的 `{name}` 占位符。
- 请求以提取基线为准并应用设计 `patch`：`remove` 后字段不存在，`add/replace` 后字段值等于补丁值。反向和越界用例不得把设计删除或改非法的值修复回合法值。
- `expected.statusClass` 翻译为两条状态码断言：`2xx` 使用 `status_code gte 200` 和 `status_code lt 300`；`4xx` 使用 `status_code gte 400` 和 `status_code lt 500`。
- 设计 `expected.assertions` 原样写入 `assertRules`；不增加设计之外的业务断言。
- 不生成 `extractRules`。
- 设计 `patch` 使用 `json` 时 `bodyType: json`；使用 `data` 时 `bodyType: form`。
- `orderNo` 使用 `batch.startOrderNo` 起的全局序号，逐条递增。
- 继续优化时以 `currentYaml` 为基线，只修改 `revisionInstruction` 要求的内容，不增删本批用例。
