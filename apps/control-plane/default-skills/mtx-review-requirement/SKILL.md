---
name: mtx-review-requirement
description: 对原始需求材料做提示性评审，输出问题登记表、覆盖度和摘要 JSON。用于需求评审、需求质检、需求缺口与冲突识别；不生成测试用例，也不判断需求是否值得做。
---

# 需求评审

读取平台提供的原始需求文档和图片，输出一份结构化评审报告。报告只用于帮助人识别需求中的冲突、歧义、缺失、弱验收标准、不可测和输入缺口，不阻断后续材料提取，也不替代人工评审。

## 输入

平台以 JSON 文本传入以下字段：

- `sourcePath`：原始需求文件路径，只读；Word/DOCX 或富文本 HTML。
- `documentType`：`word` 或 `richtext`。
- `sourceName` / `sourceLocation`：正式来源名称和稳定定位；临时路径不得写入报告来源。
- `images`：富文本图片映射，包含 `fileId`、`sourcePath`、`sourceLocation`；需要读取图片中的可见文字和业务含义。
- `revisionInstruction`：本轮用户说明。修订时只依据它和已有报告更新，不推测未回答的内容。
- `currentArtifact`：修订时的上一版评审报告。

## 按需加载

- 首次评审起草前必须读取并遵循 [主提示词](prompts/requirement-review.md)。
- 修订时读取并遵循 [修订提示词](prompts/requirement-review-revision.md)。
- 输出前必须在同一次任务中读取并执行 [输出前自查](prompts/requirement-review-self-review.md)，修正可修复问题；不额外输出自查报告。
- 需要判定问题类型、证据写法或覆盖度时，按需读取 [问题类型](references/issue-types.md)、[证据规则](references/evidence-rules.md)、[检查清单](references/checklist.md)。

## 输出

固定契约以 [output.schema.json](references/output.schema.json) 为准，不添加未定义字段。报告只包含：

- `reviewStatus`：`passed`、`needs_clarification` 或 `blocked`。
- `summary`：评审范围、已读材料、已确认事实、工作假设、待验证假设、输入缺口。
- `issues`：唯一的 `RR-xx` 问题登记表。
- `coverage`：结构盘点、质量特性、需求气味、行为完整性、追溯和输入审计。

平台提供产物交接路径时，将完整 JSON 保存到该文件，并只返回固定文件回执 `{"artifactFile":"requirement-review.json"}`。没有提供交接路径时直接返回完整 JSON。保存后运行：

```bash
python <skill目录>/scripts/validate.py <输出文件>
```

脚本校验 JSON 语法、重复键、Schema、ID 唯一、严重度证据、状态一致性和覆盖度引用。校验失败时修正后再次校验，不能把未通过校验的结果声称为正式产物。Schema 和脚本检查不能证明业务语义、原文引用或图片识读正确，仍需人工判断。

## 报告原则

- 只输出一份 `issues` 登记表；不要另写“缺口与歧义”“跨源冲突”“TOP 3 风险”等多份重叠清单。
- 每个 issue 的 `question` 就是待确认问题；不要增加顶层 `questions` 数组。
- 严重度使用 `blocker` / `major` / `minor`，不给 0–100 分、RPN 或红绿灯。
- `blocked` 至少一个 blocker；`needs_clarification` 没有 blocker 且至少一个 major；`passed` 没有 blocker/major，允许 minor。
- 不编造接口、SLA、字段、状态或根因；不把假设写成已确认事实；不替用户决定业务规则。
- 不判断需求值不值得做，不生成测试用例、测试点或执行结论。

## 边界

本技能不是测试用例生成器，不是自动化执行器，也不是需求价值评审。它只整理可核对的评审发现，最终是否修改需求、是否继续下游由人决定。
