# control-plane 开发指引

本目录遵循根目录 [AGENTS.md](../../AGENTS.md)。文档统一维护于 [docs/control-plane](../../docs/control-plane/README.md)。

- 业务上下文：[CONTEXT.md](../../docs/control-plane/CONTEXT.md)。
- 架构决策：[ADR](../../docs/control-plane/adr/)。
- 开发或审查代码、接口及迁移前，阅读并遵循[通用后端规则](../../docs/agents/backend-development.md)和[控制面开发规则](../../docs/control-plane/development-rules.md)，按变更类型选择验证入口。
- 公共规范：[领域文档](../../docs/agents/domain.md)、[问题跟踪](../../docs/agents/issue-tracker.md)、[分诊标签](../../docs/agents/triage-labels.md)。

问题跟踪路径 `.scratch/` 相对单仓库根目录；应用代码与测试路径相对本目录。修改业务代码前先阅读对应上下文和相关 ADR。
