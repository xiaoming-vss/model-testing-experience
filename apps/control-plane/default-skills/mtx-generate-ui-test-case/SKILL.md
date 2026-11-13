---
name: mtx-generate-ui-test-case
description: 根据已审核的 UI 场景设计、正式功能用例和前端源码生成平台 UI 用例 YAML，也可对调用方提供的候选 YAML 返回语义复核意见。
---

# UI YAML 生成

## 输入

生成输入包括源码目录、当前模块的正式功能用例、已审核的 UI 场景设计与元素清单，以及执行上下文。收到当前阶段产物和修订要求时按本轮范围修订。

## 执行

- 明确要求只读复核（例如 taskMode=review）时，读取 [语义复核提示词](prompts/yaml-advisory-review.md)。只有 candidateYaml 且没有明确生成或修订意图的旧调用，继续按只读复核处理；明确修订请求以该候选为起点，不因字段名误转为复核。
- 生成或修订时读取 [主提示词](prompts/yaml-generation.md)，导出前执行 [输出前自查](prompts/yaml-self-review.md)。

## 输出与校验

正常生成与修订按 [平台格式](references/platform-format.md) 返回完整 YAML 列表；语义复核返回调用方规定的 JSON 报告。执行能力及输入输出示例见 [能力说明](references/execution-profile.md) 和 [链路示例](references/pipeline-examples.md)。

若 included 目标缺少必需执行能力，停止成功导出并报告 DESIGN_CONFIRMATION_REQUIRED、caseId/目标 ID、具体缺口及需确认事项；候选缺陷尚未修复时报告 GENERATION_INCOMPLETE。优先使用调用方已有失败通道；未提供时返回明确失败说明。失败说明不属于可导入 YAML，不输出部分 YAML 冒充成功，不修改已审核设计。普通可补全定位/数据缺口仍按 missingFields 交付草稿。
