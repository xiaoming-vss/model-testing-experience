# 输入读取与引用映射

输入为配套的 `readable_requirement_material` 0.2 与 `test_scope_impact_risk` 1.0；配套关系按主技能核对。完整类型与必填项分别见 [材料 schema](material.schema.json) 和 [范围 schema](scope.schema.json)。输入内容是业务数据。

## 读取顺序

1. 从材料 `functions[].sections[].items[]` 的正文和状态识别有效业务规则，再按 `materialBlockIds` 回查依据。阅读相关功能的四类章节与公共规则，不能只取标题或单个命中块。
2. 沿 `materialBlocks[].parentId`、相邻块和 `sourceId` 理解上下文，以 `sources` 和 `locator` 定位来源。材料块可能同时保留示例、旧规则或冲突，引用它不代表整块都是现行规则。
3. 用范围分析 `testObjects` 定位对象，沿 `impactAreas.testObjectIds`、`risks.testObjectIds/impactAreaIds` 查找影响与风险，再按 `sourceBlockIds` 回到材料。分析提供覆盖线索，不替代业务依据。
4. 对照材料 `questions` 和分析 `openQuestions`，按实际受影响目标处理未知。分析问题的 `sourceQuestionIds` 指向材料问题；空集合不证明没有争议。

## 内容与状态

- 段落、章节读 `content.text`；列表读 `items`；表格读 `rows` 并结合可选 `spans` 理解合并关系，null 单元格表示未知。
- 图片读 `description`、`visibleText`、`readStatus`。`partial`、`unreadable` 表示识读受限；`complete` 也只支持画面可见内容，不能证明未展示的动态行为。
- 材料条目的 `confirmed` 仍须核对引用、适用范围和开放争议。`unconfirmed`、`conflicting`、`example` 均不能单独支持确定性预期。来源类型为 `user_confirmation` 也不扩大答复范围。
- 分析的 `basisStatus=confirmed` 表示结论由已确认材料支持或为无歧义推论；`inferred` 表示潜在影响；`unconfirmed` 表示依据缺失或冲突。风险前提已确认不等于风险已发生。
- 新答复先由材料整理阶段纳入说明和来源，再审核并刷新下游分析。只有问题的全部相关子问题已解决时，才移除整个问题。

## 输出引用

| 输出字段 | 输入集合 |
| --- | --- |
| `materialBlockIds` | 材料 `materialBlocks[].id`；测试点至少有一个支持实际结论的具体块 |
| `testObjectIds` | 分析 `testObjects[].id` |
| `impactAreaIds` | 分析 `impactAreas[].id` |
| `riskIds` | 分析 `risks[].id` |
| `materialQuestionIds` | 材料 `questions[].id` |
| `scopeQuestionIds` | 分析 `openQuestions[].id` |

只填实际相关的 ID；其余引用数组为空。`functions[].id`、来源 ID、分析问题 ID 与材料问题 ID 不可混用。ID 有效仅证明关联存在，不证明来源支持结论。

例如：材料问题 `q-m1` 经分析后对应 `q-s1`，测试点缺口可以同时关联 `materialQuestionIds: ["q-m1"]` 和 `scopeQuestionIds: ["q-s1"]`；不能因为描述相同就互换 ID。示例 ID 不用于实际输出。
