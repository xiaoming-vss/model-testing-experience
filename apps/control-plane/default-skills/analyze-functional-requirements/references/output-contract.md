# 输出结构与字段语义

下列是结构模板，数组对象表示条目形状，不要求生成占位记录。实际输出填入分析内容，无条目的数组用 []。所有层级的 key 固定：不得增加、删除、改名或翻译字段。同类条目必须保留全部字段。

生成前必须读取 [../assets/output-template.json](../assets/output-template.json)，以它作为输出结构模板。下方带注释的内容仅用于解释字段，不是实际输出格式。实际响应只能包含一个标准 JSON 对象，不能包含注释、Markdown 代码围栏、前言、结语或其他文字。

```jsonc
{
  "functionalOverview": { // 功能概况
    "purpose": null, // 功能目的；未明确时为 null
    "applicableObjects": [], // 适用业务对象
    "actors": [], // 操作角色
    "entryPoints": [ // 操作入口
      {
        "function": null, // 对应功能，必要时标明模块
        "path": null, // 端及页面路径
        "action": null // 用户操作
      }
    ],
    "explicitExclusions": [] // 明确排除的范围；空数组表示未列出
  },
  "scenarioFactors": [ // 场景划分因素
    {
      "factorId": "F01", // 因素编号
      "name": null, // 因素名称
      "confirmedValues": [], // 已明确取值，不代表穷尽所有可能
      "defaultValue": null, // 默认值；未知或不适用时为 null
      "clarificationNeeded": null // 需确认内容；无已识别问题时为 null
    }
  ],
  "businessRules": [ // 独立业务规则
    {
      "ruleId": "R01", // 规则编号
      "category": null, // 如入口与权限、主流程、状态变化、生效范围、异常与恢复
      "name": null, // 规则名称，不是最终用例名称
      "confirmationStatus": "需求明确", // 需求明确、基于规则推导、待确认
      "applicableObject": null, // 适用对象
      "preconditions": [], // 前置条件
      "trigger": null, // 操作或事件；静态规则无触发时为 null
      "expectedBehavior": [], // 预期处理，存在先后关系时按顺序排列
      "prohibitedOrSkippedBehavior": [], // 禁止或应跳过的行为
      "observableOutcome": null, // 可验证的页面、数据、设备或记录结果；明确时使用中文字符串
      "sourceReferences": [], // 原文章节或可定位的段落；无章节时使用真实标题及简短摘录
      "relatedQuestionIds": [] // 关联待确认问题编号
    }
  ],
  "scenarioBreakdown": [ // 供测试点编写使用的场景
    {
      "scenarioId": "S01", // 场景编号
      "relatedRuleIds": [], // 关联规则编号；实际场景至少关联一条规则
      "derivationType": "需求直接描述", // 需求直接描述或基于规则推导
      "conditions": [], // 具体条件组合，包括必要的对象、渠道及状态
      "trigger": null, // 触发操作或事件
      "verificationObjective": null, // 核心验证目标；预期无法确定时为 null
      "readyForTestPointGeneration": false, // 能否生成条件与验证目标明确的测试点名称
      "blockingReason": null, // false 时说明原因；true 时为 null
      "relatedQuestionIds": [] // 关联问题，不一定阻塞名称编写
    }
  ],
  "openQuestions": [ // 需求缺口与影响
    {
      "questionId": "Q01", // 问题编号
      "question": null, // 可独立回答的问题
      "affectedScope": null, // 受影响规则、场景或分析范围
      "blockedWork": null // 具体阻塞的工作，如预期、步骤或检查方法
    }
  ]
}
```

## 类型与填写约束

- `defaultValue` 可为字符串、数字、布尔或 null；其他非集合描述字段为字符串或 null。`readyForTestPointGeneration` 为布尔值。集合始终为数组，描述与引用数组元素均为字符串。
- ID 使用 F01、R01、S01、Q01 格式递增，各集合条目数量不必相同。
- 实际条目的编号、名称、类别、明确程度、问题正文等必须有内容，不保留模板占位记录。未确认规则保留已知部分并关联问题。
- 空数组只表示没有已明确条目，不等于已确认无约束或无影响。
- 可生成标记为 true 必须有具备依据的验证目标；缺检查手段或精确操作节点，可关联问题而不阻塞名称编写。缺少决定预期的规则时为 false。
- false 场景必须有阻塞原因及对应问题引用；不能同时填写未知预期与肯定可生成。

## 跨阶段缺口语义

保持原有字段集合。openQuestions 的 blockedWork 明确描述缺失类别（业务预期、操作路径、观察证据、判定标准）、受影响目标及阶段；缺口类别写在现有字符串内，不新增字段。affectedScope 定位对应规则、场景及必要条件，避免只写整个模块。

例如：已确认新增格式可以执行转换，但发起方式未知，可将 readyForTestPointGeneration 设为 true，并关联问题，其 blockedWork 写“操作路径：阻塞新增格式转换用例的发起步骤；不阻塞该能力测试点名称生成”。这不授权下一阶段自行增加界面选项。

已有提示要求但文案未知，仍可验证提示存在；没有提示要求时不能由必填规则推定必有提示。缺失观察工具不等于没有业务要求，已知目标应保留；未知证据来源也不能被“符合预期”补齐。用户的明确业务答复可更新相应问题，未回答的问题继续保留。

## 性能与长稳语义

不新增 key 或枚举值。使用已有字段区分两类目标：

- 指标验收：businessRules 的 expectedBehavior 保存已确认指标及适用条件，observableOutcome 保存已知指标证据；没有确认的阈值不补造。verificationObjective 明确要验证的指标，缺少决定达标与否的标准时不能把达标目标标为 ready。
- 基线测量：须有用户或材料明确提出的评估范围。场景关联被测业务的真实规则，derivationType 按直接要求或规则推导填写；verificationObjective 明确“基线测量”及测量对象、指标或趋势，不写未知的合格结论。不得为了满足 relatedRuleIds 而虚构质量规则或将测量结果写成业务保证。sourceReferences 可引用实际提供的评估请求，不能伪造 PRD 章节。
- 测量对象及指标明确而执行负载、时长或采样手段尚未确定时，可生成名称，关联问题并在 blockedWork 说明阻塞完整测量用例，不阻塞名称；完全不知评估对象时先记录问题。仅缺产品合格阈值，不阻塞已明确要求的基线测量。
- scenarioFactors.confirmedValues 仅记录已确认值；建议的并发、持续时间等不能写成已确认值。缺失项通过 clarificationNeeded/openQuestions 表达。不将所有可能指标或工具列为必答问题，只询问与当前目标执行或判定直接相关的缺口。

例如：用户要求评估批处理吞吐但未设性能标准，场景可写“基线测量：记录不同输入规模下批处理的完成吞吐量”，负载档位未定的问题影响执行配置；不能生成“吞吐量达到每秒一千条”。同样，持续运行测量可以记录资源增长趋势，但没有判定依据不能写成“无内存泄漏”。

## 场景与来源语义

- conditions 中各项同时成立；独立分支按 SKILL.md 的场景拆分规则处理。verificationObjective 表达该条件下的核心判断，不以“分别验证全部情况”代替具体分支。
- relatedRuleIds 包含决定该场景预期的全部规则；同一触发的关联结果可共用一个场景。规则 ID 被引用不代表其全部行为已覆盖。
- derivationType 按整个场景的形成方式填写：输入直接给出了条件、事件及结果时用“需求直接描述”；分析者组合多条规则、构造边界或反向条件时用“基于规则推导”。推导场景仍需完整依据。
- sourceReferences 在真实来源定位后可附上游 R/O/C/EV 等 ID；输出自身 ruleId/scenarioId 独立编号，不要求与上游一一对应。
- 聚合能力已确认但计算方式未知时，可生成关于聚合对象范围的测试点；精确数值正确性若无判定依据，应单独关联问题，不能以“按规则聚合”充当确定的数值预期。已知目标缺操作或观察细节，仍按跨阶段缺口语义处理。
