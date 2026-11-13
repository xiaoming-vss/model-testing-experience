---
name: mtx-map-functional-cases-to-ui-scenarios
description: 依据正式功能用例设计 UI 操作与断言，保留原始用例的业务目标和来源，按平台能力标记覆盖与排除。
---

# UI 场景设计

## 输入

需求画板提供当前模块的正式功能用例、源码目录、已审核的 UI 元素清单、能力约束和任务上下文。正式用例决定设计范围。元素清单用于辅助理解页面术语。

## 执行

1. 读取 [主提示词](prompts/scenario-design.md)，逐条设计本模块用例。
2. 候选完成后执行 [输出前自查](prompts/scenario-self-review.md)，核对来源、能力约束和完整性。输入输出与下游交接见 [链路示例](references/pipeline-examples.md)。

## 输出与校验

按 [输出 Schema](references/output.schema.json) 和 [业务契约](references/contract.md) 直接返回当前模块的完整 `ui_test_scenarios/2.0` JSON。调用方提供 Schema 时按其约束交付。
