# studio 开发指引

本目录遵循根目录 [AGENTS.md](../../AGENTS.md)。文档统一维护于 [docs/studio](../../docs/studio/README.md)。

- 业务上下文：[CONTEXT.md](../../docs/studio/CONTEXT.md)。
- 结构与代码规范：[STRUCTURE.md](../../docs/studio/STRUCTURE.md)（分层与依赖方向、feature 边界、样式归属、目录契约、代码体积）。
- 修改页面布局、背景、边距或工具栏时，必须先读 [界面规范](../../docs/studio/UI-GUIDELINES.md)，复用全站公共样式，并检查同类页面一致性。
- 架构决策：[ADR](../../docs/studio/adr/)。
- 公共规范：[领域文档](../../docs/agents/domain.md)、[问题跟踪](../../docs/agents/issue-tracker.md)、[分诊标签](../../docs/agents/triage-labels.md)。

问题跟踪路径 `.scratch/` 相对单仓库根目录；应用代码与测试路径相对本目录。修改业务代码前先阅读对应上下文和相关 ADR。
