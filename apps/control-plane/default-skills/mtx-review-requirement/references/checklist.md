# 需求评审检查清单

## 输入审计

- [ ] 已读取 Word 正文、表格和嵌入图片，或富文本正文和 `images`。
- [ ] 已确认 `sourceName`、`sourceLocation` 可用，报告中没有临时路径。
- [ ] 结构盘点覆盖：背景、目标、用户故事、功能、NFR、边界、验收标准、KPI、依赖、时间线、原型。
- [ ] 材料过薄、章节缺失、图片不可读时已登记 `input_gap`。

## 质量特性

- [ ] 单条语句检查：无歧义、单一要求、完整、可验证、必要。
- [ ] 集合级检查：一致、完整。
- [ ] 失败项都进入 `issues`，并在 `coverage.qualityCharacteristics` 中用 `issueIds` 引用。
- [ ] 通过项没有引用 issue。

## 需求气味

- [ ] 检查 vague / optional / subjective / loophole / unbounded / compound / tbd。
- [ ] 每条气味引用原句，并关联存在的 issue。
- [ ] 没有为了凑数登记无关气味。

## 行为完整性

- [ ] 状态迁移、初始态、终态、回退。
- [ ] 判定条件、分支、优先级、互斥。
- [ ] 超时、时效、幂等、重复提交、并发。
- [ ] 失败路径、重试、降级、补偿。
- [ ] 空态、加载、错误、禁用、提示和可观察结果。
- [ ] 缺口写入 `coverage.behavioralStates`，影响交付/测试的进入 issues。

## 追溯

- [ ] 规则没有验收标准 → `rule_without_ac`。
- [ ] 验收标准没有规则 → `ac_without_rule`。
- [ ] 目标没有功能 → `goal_without_feature`。
- [ ] 功能没有目标 → `feature_without_goal`。
- [ ] fail 项引用 issue；pass 项不引用 issue。

## 冲突

- [ ] 文档内部矛盾已检查。
- [ ] 冲突保留双方原文和定位，没有自动裁决。
- [ ] 文档版本或时效不明时写入输入审计或 `input_gap`。

## 可测性

- [ ] 缺少可观察失败条件/判定依据的条目标为 `untestable`。
- [ ] 每个 blocker 都有 `failureMode`。
- [ ] 没有伪 RPN、百分制、红绿灯或需求价值判断。

## 输出

- [ ] 只有一份 `issues` 登记表，没有多份重叠清单。
- [ ] 没有顶层 `questions`、`clarifications`、`riskAcceptance`。
- [ ] `reviewStatus` 与 issue 严重度一致。
- [ ] 完整 JSON 已保存到交接路径并通过 `scripts/validate.py`。
