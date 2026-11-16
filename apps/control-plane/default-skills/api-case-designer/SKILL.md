---
name: api-case-designer
description: 基于已审核的接口配置提取 JSON 设计 API 接口用例，逐接口产出正向、反向和边界场景。每条用例包含结构化依据 basis、参数变异 patch 和预期状态与断言；输出 api_test_design/1.0 JSON，供后续 YAML 生成阶段逐条落地。
---

# API 接口用例设计

把已审核的接口配置提取产物转换为可审核的用例设计。设计只使用提取产物中的接口事实和调用方给出的需求上下文，不读取接口 description/tags、源码或仓库。

开始前读取 [输入契约](references/input-format.md)、[覆盖规则](references/coverage-rules.md) 和 [输出格式](references/output-format.md)。

## 输入

- `apiExtraction`：本批接口的提取子集，键为 snake_case 接口名。
- `requirement`：需求 ID、名称和生成要求。
- `batch`：本批序号、总批数和接口名列表；只设计 `batch.interfaceNames` 中的接口。
- 继续优化时额外包含 `currentDesign`（本批当前设计）和 `revisionInstruction`。

## 执行

- 为每个接口设计 1 条全参数正向用例；存在可选字段时再设计 1 条仅必填最小参数正向用例。
- 按 [覆盖规则](references/coverage-rules.md) 设计必填缺失、类型非法、枚举/格式非法和边界用例。
- 每条用例写明 `basis`：引用提取产物中实际存在的字段、必传标记、类型或约束原文。
- 参数变异用 `patch` 表达：按 `headers/path_params/query/json/data` 分区，路径是相对该分区的 JSON Pointer。
- 正向和边界内预期 `2xx`，反向和越界预期 `4xx`；不假设精确错误码，不编造错误响应字段。
- 超出目标或价值较低的约束写入 `uncovered`，不静默丢弃。
- 继续优化时以 `currentDesign` 为基线，只修改 `revisionInstruction` 要求的内容；未涉及用例保持原样。

## 输出与校验

只返回一个可由 JSON.parse 直接解析的 JSON 对象，`schemaVersion` 固定为 `api_test_design/1.0`。不返回 YAML、Markdown 代码块、解释文字或第二个 JSON 对象。

平台会校验接口集合、method/path、id/title 唯一性、basis 引用、patch 可应用性、预期状态、断言上限和覆盖规则；校验失败时按错误修正，不编造提取产物中不存在的字段或约束。
