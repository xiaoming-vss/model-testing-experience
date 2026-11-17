# 输出前自查

在保存或返回最终 JSON 前，逐项检查并修正。不要输出自查报告，只输出修正后的正式产物。

## 结构

- 顶层只有 `schemaVersion`、`artifactType`、`reviewStatus`、`summary`、`issues`、`coverage`。
- `schemaVersion` 为 `1.0`，`artifactType` 为 `requirement_review`。
- `summary` 包含 `scope`、`materialsReviewed`、`confirmedFacts`、`workingAssumptions`、`hypothesesToVerify`、`inputGaps`。
- `coverage` 包含 `structure`、`qualityCharacteristics`、`smells`、`behavioralStates`、`traceability`、`inputAudit`。
- 没有 `questions`、`clarifications`、`riskAcceptance` 或其他未定义字段。

## 状态与严重度

- 至少一个 blocker → `blocked`。
- 没有 blocker、至少一个 major → `needs_clarification`。
- 没有 blocker/major（允许 minor）→ `passed`。
- 状态与 `issues` 的严重度一致，不能出现“有 blocker 但 passed”。

## 问题证据

- 每个 issue 的 `id` 唯一，格式为 `RR-xx`。
- 每个 blocker 都有非空 `failureMode`。
- 每个 blocker/major 至少一条 evidence，且 `quote` 非空。
- `evidence.sourceName` 和 `locator` 能定位到原文；不使用临时路径、签名 URL。
- `question` 是具体、可回答的问题，不是泛泛而谈。
- `suggestedOwner` 和 `verifyMethod` 使用 schema 允许的值。

## 覆盖度引用

- `coverage.qualityCharacteristics[].issueIds` 都引用存在的 issue。
- `qualityCharacteristics` 为 `fail` 时至少引用一个 issue；为 `pass` 时不能引用 issue。
- `coverage.smells[].issueId` 都引用存在的 issue，`quote` 来自原文。
- `coverage.traceability` 为 `fail` 时必须有 `issueId` 且引用存在；为 `pass` 时不能引用 issue。
- `coverage.inputAudit` 的 `materials`、`missing`、`recency`、`comparability` 如实填写；只审文档内部一致性时明确说明。

## 事实与边界

- `confirmedFacts` 只包含原文明确、可追溯的事实；用户说明或模型推断不能写成已确认事实。
- `workingAssumptions` 和 `hypothesesToVerify` 与 `confirmedFacts` 分开。
- 输入缺口写进 `inputGaps` 或 `input_gap` issue，不假装审完。
- 不编造接口、SLA、字段、状态、根因或业务规则。
- 不输出测试用例、测试点、执行结论或需求价值判断。

## 最后一步

- 将完整 JSON 保存到平台提供的交接路径（如有），运行 `scripts/validate.py`，修正所有错误后再返回。
- 校验通过不等于业务语义正确；仍需人工对照原材料核查。
