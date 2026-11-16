# 输出前自查

返回结果前逐项确认：

- 输出是单个 JSON 对象，`schemaVersion` 为 `api_test_design/1.0`。
- `interfaces` 只包含 `batch.interfaceNames`，method/path 与提取产物一致。
- 每个接口至少有一条全参数正向用例；存在可选字段时有一条仅必填正向用例。
- 每条用例都有唯一的 `id` 和 `title`，`intent` 非空。
- 每个非正向依据的 `section/field/constraint` 都能在提取产物中找到。
- 必填缺失用例在对应字段执行 `remove`，一次只缺一个字段。
- 边界用例只使用 `minimum/maximum/minLength/maxLength`，并成对覆盖边界内和越界。
- 正向/边界内为 `2xx`，反向/越界为 `4xx`。
- `4xx` 的 `assertions` 为空；`2xx` 最多 2 条且不含 `status_code`。
- 超出数量上限的约束写入 `uncovered`，且没有被某条用例同时覆盖。
- 没有 Markdown 代码块、解释文字或第二个 JSON 对象。
