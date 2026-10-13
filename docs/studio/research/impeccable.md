# Impeccable 项目调研

调研日期：2026-10-08；来源快照：[`778c8a7`](https://github.com/pbakaus/impeccable/tree/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d)。仅阅读官方文档与源码，未安装、运行或验证效果。

## 定位与能力

Impeccable 为 AI 编程工具补充设计指导、命令工作流和自动检测。当前 README 列出 1 个 skill、24 个命令及 59 条确定性规则；`init` 记录产品事实到 PRODUCT.md，视觉系统另存 DESIGN.md。适合用 `audit` 找质量问题、`critique` 讨论层次与体验、`clarify` 改文案、`harden` 补边界、`polish` 做交付前整理。[README](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/README.md)

## 技术架构

当前运行时是 Rust 工作区：检测分文本、静态 HTML、浏览器 URL 三条路径；共享规则通过 WASM 进入页面和扩展。npm 包主要负责定位或下载二进制，规则检测无需 LLM/API key，设计生成仍依赖宿主 AI。URL 检测需要 Chrome、Chromium 或 Edge；结果支持 JSON 和不同退出码。[引擎架构](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/docs/ENGINE.md)、[CLI 文档](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/README.npm.md)

Live 模式把浏览器选中元素、localhost 服务、AI 生成源码变体连接起来，通过开发服务器预览，再接受或丢弃；代理需持续处理轮询事件。它要求本地源码和开发环境，不能直接编辑线上站点。旧 Live ADR 的 Node 服务描述已经落后于当前 Rust 实现，不能据此判断现状。[Live 工作流](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/skill/reference/live.md)、[历史 ADR](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/docs/adr-live-variant-mode.md)、[引擎架构](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/docs/ENGINE.md)

## 边界与 Studio 适配判断

“确定性”表示规则可重复执行，不代表审美结论客观正确。规则同时涵盖对比度、触控尺寸等质量指标，以及常用字体、渐变、卡片嵌套等风格偏好；扫描通过也不能证明业务体验或完整可访问性合格。[规则示例](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/README.npm.md)

建议先在 Studio 单页试用 audit / clarify / harden / polish，保留既有配色、主题 token、信息密度与业务行为；不要把全部审美规则直接作为 CI 硬门禁。引入 PRODUCT.md / DESIGN.md 时应遵守本仓库文档归属，避免与现有规范重复维护。最终仍需现有主题检查、相关测试和真实浏览器验收。这是结合本地规范的适配判断，并非已验证的接入结果。[Studio UI 规范](../UI-GUIDELINES.md)、[主题 ADR](../adr/0002-token-based-github-dark.md)
