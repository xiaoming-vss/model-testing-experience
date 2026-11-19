# ADR 0018：需求评审作为提示性首阶段

- 状态：已接受
- 日期：2026-11-16
- 取代：—
- 被取代：—
- 关联：[需求生成链](../generation-chain.md)、[需求分析审核规则](../requirement-analysis-review.md)、[需求分析两阶段设计](../../ai-worker/requirement-analysis-two-stage-design.md)

## 背景

需求分析链原先只有 `extracting_text`（材料整理）一个阶段，只整理材料，不在最前面识别需求本身的冲突、歧义、缺失、弱验收标准和输入缺口。评审报告如果直接作为材料提取的硬前置，需要额外的解释闭环、风险接受、文档哈希绑定和跨阶段消费协议。

本次先验证评审报告的识别效果，不把它接入下游，也不让它阻断材料整理。

## 决策

1. 在 `requirement_analysis` 链最前面新增 `requirement_review`（需求评审）阶段，产物类型为 `requirement_review` 1.0，配置字段为 `reviewOutput`，文件回执为 `requirement-review.json`。
2. 评审是提示性的：
   - 任何 `reviewStatus` 都可以审核通过和审核通过并继续。
   - 不实现 `accepted_with_risk`、`riskAcceptance` 或风险接受理由。
   - 不实现 `clarifications`、issue `resolved` / `accepted_risk` 或逐条解释闭环。
   - 不校验需求文档哈希，不做提取门禁。
3. `extracting_text` 与 `requirement_review` 独立：
   - `extracting_text` 没有上游阶段，不要求评审版本。
   - 材料提取不读取评审产物，不做 `src-RC-xx` 覆盖校验。
   - 删除评审版本不影响材料提取版本或草稿。
4. 评审报告保留完整内容：`reviewStatus`、`summary`、`issues`、`coverage`。`reviewStatus` 只由 issue 严重度计算，用于展示。
5. 新增默认技能 `mtx-review-requirement`；同一份 Schema 在控制面、AI Worker 和技能目录各保留一份，并由一致性测试防止漂移。
6. 不新增数据库表、列或迁移；阶段名、产物、评审版本都落在现有生成链结构。

## 后果

- 用户可以先跑评审看效果，也可以直接跑材料提取；两者互不阻塞。
- 评审报告的问题登记表、覆盖度和证据可供人工判断，但不影响后续阶段输入。
- 后续如果决定让材料提取消费评审结论，需要重新讨论上游依赖、clarification 语义和覆盖校验，并新增契约或版本；本次不预埋这些字段。
- 控制面、AI Worker 和 Studio 需要一起发布；新默认技能需要通过 `python -m testing_agent.cli.skills default-skills` 或 Helm `skillsSync` 同步到 S3。
- 旧需求仍可直接重跑材料提取；旧材料版本和功能链不受影响。

## 备选方案

- **硬门禁 + 解释闭环 + 风险接受**：状态和跨阶段协议更复杂，且当前尚未证明评审报告的质量；暂不采用。
- **独立评审任务**：无法复用现有阶段版本、审核和继续优化交互；不采用。
- **评审结果传给材料提取**：需要额外的 clarification 和覆盖校验，当前先观察评审效果；后续再评估。
