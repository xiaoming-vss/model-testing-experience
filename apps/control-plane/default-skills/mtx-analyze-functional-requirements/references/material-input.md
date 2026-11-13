# 材料整理 JSON：字段与使用方式

输入来自材料整理 skill 的 `readable_requirement_material` 0.2 产物。分析时以这份输入的实际内容为准；完整格式见本包 [材料 schema](material.schema.json)，发布时与材料整理的输出契约同步。此处说明测试对象、影响和风险分析如何使用字段，不另造事实来源。

## 顶层字段

| 字段 | 含义与分析用途 |
| --- | --- |
| `schemaVersion` | 材料整理输出版本，当前接受 `"0.2"`。 |
| `artifactType` | 产物类型，当前接受 `"readable_requirement_material"`。 |
| `title` | 整理后的材料标题，用于识别分析对象；标题本身不能证明具体行为。 |
| `sources` | 来源清单；按来源 ID 识别原文档、图片或明确的用户补充。 |
| `materialBlocks` | 按原材料顺序保留的材料块；分析时回查原文、位置、表格、图片识别状态及上下文，并用块 ID 追溯依据。 |
| `functions` | 按功能组织的可读整理结果，是识别功能、对象和业务关系的入口；每条说明有状态和材料块引用。 |
| `questions` | 材料整理阶段尚未解决的问题，供影响和风险分析关联；空数组只表示该产物没有记录问题，不证明材料没有歧义。 |

## 来源与材料块

- `sources[]` 的 `id` 是来源标识；`name` 是来源名称；`type` 为 `document`、`richtext`、`image` 或 `user_confirmation`；`location` 是稳定位置或 `null`。来源名称或类型不自动证明其中每项内容均已确认；用户补充只适用于其明确覆盖的对象和范围。
- `materialBlocks[]` 的 `id` 是本次输出 `sourceBlockIds` 的引用目标；`sourceId` 指向 `sources[].id`；`parentId` 指向父材料块，顶层为 `null`；`locator` 用于定位原材料；`kind` 和 `content` 表示内容形式。可沿父块和相邻材料回查语境，结论应引用实际支持该结论的具体块，不只引用标题或来源 ID。
- `kind` 为 `section` 或 `paragraph` 时，`content.text` 为文本；为 `list` 时，`content.items` 为字符串列表；为 `table` 时，`content.rows` 保留行列，`null` 表示未知单元格，可选 `spans` 描述合并单元格；为 `image` 时，`content.description`、`visibleText`、`readStatus` 分别记录识别说明、与需求相关的可辨认文字及读取状态。
- 图片 `readStatus` 为 `complete`、`partial` 或 `unreadable`。`partial` 和 `unreadable` 表示相关内容可能不完整；即使是 `complete`，静态截图也只支持可见信息，不能据此推断未显示的动态行为。截图示例、旧界面信息和需求目标要按材料语境区分。
- 材料块保留原始信息，并非每块都代表现行或已确认规则。必须结合功能说明的状态、来源语境以及可能存在的冲突判断；示例、历史内容和待确认事项不能单独当作现行事实。

## 功能说明与确认状态

- `functions[]` 的 `id`、`name` 标识功能；`sections[]` 按有内容的类别组织，`title` 为“功能目标与背景”“页面入口”“功能使用与业务规则”或“完整业务流程”，`items[]` 为各条说明。
- 每个 `item` 包含 `text`、`status` 和 `materialBlockIds`。先以 `text` 找到分析对象，再按 `materialBlockIds` 回查原材料的具体条件、对象、例外与来源；功能 ID 不是材料块 ID，不能放入 `sourceBlockIds`。
- `status` 为 `confirmed` 表示该说明在整理结果中标为已确认，但仍须确认引用实际支持当前结论及其适用范围；`unconfirmed` 表示未确认，`conflicting` 表示存在冲突，`example` 表示示例。后三类不得直接作为确定性行为。即使一个块同时被不同状态的说明引用，也应结合具体说明和上下文判断，不要把块本身永久归类为已确认。
- 对象、影响和风险输出中的 `basisStatus` 是对**分析结论**的判断，与输入 item 的 `status` 不是一对一复制：`confirmed` 需全部关键内容有已确认依据；潜在影响使用 `inferred`；事实缺失、冲突或无法确认时使用 `unconfirmed`。风险前提已确认不代表风险必然发生。

## 待确认问题

`questions[]` 的 `id` 是原问题标识，可用于输出 `sourceQuestionIds`；`question` 是未解决的问题，`reason` 是提出原因，`materialBlockIds` 指向相关材料块，`functionIds` 指向相关功能。关联数组可以为空，不表示问题没有影响。按 [待确认问题筛选](../prompts/scope-analysis.md#待确认问题筛选) 规则筛选原问题及未答复部分，符合条件的关联对应原问题；未输出不代表原问题已解决。新发现的问题没有对应输入问题 ID 时，`sourceQuestionIds` 为空数组。
