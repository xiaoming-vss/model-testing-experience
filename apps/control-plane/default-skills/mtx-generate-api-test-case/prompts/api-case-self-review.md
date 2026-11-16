# 输出前自查

返回结果前逐项确认：

- 输出是 YAML 对象，顶层有 `cases:`。
- 输入包含 `apiDesign` 时：用例数量与 `batch.caseIds` 完全一致；`name` 等于设计 `title`，`description` 等于设计 `intent`；状态码断言与设计的 `statusClass` 一致；`extractRules` 为空；没有设计之外的业务断言；`patch` 的 remove/add/replace 效果与设计一致；反向和越界值没有被改回合法值。
- 输入没有 `apiDesign` 时：除非调用方另有要求，每个目标接口至少有一个正向用例。
- 每个用例都包含 `orderNo`。
- `orderNo` 是整数，不是带引号的字符串。
- 最终 `cases` 数组按 `orderNo` 升序排列。
- method 和 URL 映射正确。
- `bodyType` 与 `bodyJson` 匹配源请求体形态。
- `extractRules` 使用正确的 `source` 和表达式类型。
- `assertRules` 只包含可靠断言。
- 模板表达式保持 `{{...}}` 形式，没有被替换成字面值。
- 纯 YAML 输出中没有混入解释性文字或 Markdown 代码块。
