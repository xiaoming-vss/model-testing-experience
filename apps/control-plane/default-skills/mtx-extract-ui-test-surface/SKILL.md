---
name: mtx-extract-ui-test-surface
description: 读取固定版本的前端源码和正式功能用例，提取页面、控件、观察目标和定位证据，供 UI 场景设计与 YAML 生成使用。
---

# UI 元素提取

## 输入

输入为源码根目录 `sourceRoot`、选中的正式功能用例或其范围，以及调用方提供的任务上下文和可选运行时 DOM 证据。

## 执行

1. 读取 [主提示词](prompts/surface-extraction.md)，按正式用例覆盖范围查阅前端源码。
2. 候选完成后执行 [输出前自查](prompts/surface-self-review.md)，核对证据及交付路径。普通页面、定位缺口与运行时观察的完整交接见 [链路示例](references/pipeline-examples.md)。

## 输出与校验

按 [输出契约](references/contract.md) 交付 `ui_test_surface/1.0` JSON。收到 `outputPath` 时写入该路径并返回指定回执，其余情况直接返回 JSON。
