# 需求理解 2.0 输出结构

字段与类型以 [output-schema.json](output-schema.json) 为准；[output-example.json](output-example.json) 是合成示例，不代表当前产品。固定 schemaVersion="2.0"、artifactType="requirement_understanding"，只返回一个标准 JSON 对象。

## 各部分只维护自己的内容

| 位置 | 维护内容 | 关联方式 |
| --- | --- | --- |
| functionalOverview | 目的、范围、角色、明确排除 | 简短概述；事实有独立依据 |
| sources | 材料名称、类型、真实位置及已知版本 | sourceId |
| evidence | 来源定位及必要短摘录，每份证据登记一次 | id、sourceId、locator，可选 excerpt |
| businessRules | 独立规则的完整条件、触发、行为和观察依据 | moduleIds、operationIds；每条事实使用 evidenceIds |
| modules | 模块职责、入口、操作和使用顺序 | entryPoints、operations、userVisibleFlow |
| operations | 操作目标、前提、实际动作及系统响应 | ruleIds 关联规则；steps 记录执行路径 |
| interaction | 控件、选项完整性、默认值、触发、联动、结果与反馈 | 只记录当前操作独有细节，避免重复整条规则 |
| businessFlows | 跨模块主流程、异常和恢复分支 | 节点引用 moduleId/operationId，后继引用当前流程 stepId |
| questions | 剩余缺口、影响及是否阻塞 | affectedRefs 和 relatedQuestionIds |

businessFlows.nextSteps 使用 conditionRuleIds 引用已有规则，多个 ID 表示同时满足。没有对应独立规则的衔接条件才使用 condition。stepId=null 表示明确结束；nextSteps=[] 仅表示没有已记录后继。

操作 ruleIds 引用的规则必须在 operationIds 中关联该操作。模块 userVisibleFlow 只串联本模块操作，note 仅作必要衔接。ID 在其所属集合唯一，引用目标必须存在。

## 事实、概述和省略

事实对象包含 value，可选 confirmationStatus、evidenceIds、relatedQuestionIds。描述值是字符串或 null；选项值支持标量，defaultValue 还支持标量数组。

- confirmed 为事实对象的缺省状态，必须有真实证据，且不能仅由 example 来源支撑。
- unconfirmed 保留未知或部分已知内容；完全未知时 value=null。
- conflicting 必须关联证据和 open 问题。
- example 表示演示或占位；not_applicable 表示有依据的不适用，value=null。
- example、not_applicable 和 conflicting 都必须有证据。value=null 时状态必须显式填写。

普通字符串只用于 purpose、goal、actor/action/systemResponse、note 的概括或路径叙述，不能用来绕过独立事实的状态、依据或问题。

可选空集合与无记录的可选字段直接省略，如分页、排序、空态、默认值；未知、有冲突或有明确不适用结论且需要保留时使用相应事实对象。必填结构按 Schema 保留。空集合和省略字段均不证明产品不支持或没有约束。

options.items 仅包含实际已知选项；completeness 用 complete/partial/unknown/not_applicable 表达完整性，unknown 只能标记 unconfirmed/conflicting。不把截图示例当完整枚举。

## 规则去重示意

规则完整定义一次，例如 R01 记录某个阶段的准入条件。相关操作只登记 `"ruleIds":["R01"]`；流程后继可写 `{"stepId":"FN02","conditionRuleIds":["R01"]}`。控件说明、步骤响应和模块目的不再次展开该准入规则。阈值不同、作用对象不同或可以独立失败的要求不能为缩短文本强行合并。

证据例如 `{"id":"EV01","sourceId":"SRC01","locator":"第4节"}`，多条事实均可用 `"evidenceIds":["EV01"]`。只在阈值、特殊口径、冲突或确认答复需要原话时保留短 excerpt；普通背景保留定位即可。

## 问题闭环

只输出 status=open 的剩余问题；affectedRefs 定位实际受影响对象，impacts 说明剩余影响。完整答复先落实到正文，再删除问题和相关引用；部分答复仅保留剩余缺口，answer 为可省略的部分信息。审核、格式转换和重新生成不能关闭尚未回答的问题。
