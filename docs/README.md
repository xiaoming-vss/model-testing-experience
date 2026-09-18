# 文档总索引

全部项目文档统一维护在本目录。`apps/` 保存代码以及简短的 README / AGENTS 入口，避免同一说明维护多份。

## 平台公共文档

- [统一配置、部署与本地开发](deployment.md)
- [MTX 命名与旧部署兼容](naming.md)
- [领域上下文导航](../CONTEXT-MAP.md)
- [单仓库迁移说明](monorepo-migration.md)
- [验证结果与已知问题](verification.md)

## 各项目文档

| 目录 | 内容 | 对应代码 |
| --- | --- | --- |
| [studio](studio/README.md) | 前端开发、功能规格、系统设计、组件规范 | [apps/studio](../apps/studio/) |
| [control-plane](control-plane/README.md) | 控制面、API 契约、数据库与权限设计 | [apps/control-plane](../apps/control-plane/) |
| [ai-worker](ai-worker/README.md) | AI 任务、技能预置、需求与运行验证 | [apps/ai-worker](../apps/ai-worker/) |
| [api-ui-worker](api-ui-worker/README.md) | API/UI 自动化执行与 Worker 配置 | [apps/api-ui-worker](../apps/api-ui-worker/) |
| [connector-zentao](connector-zentao/README.md) | 禅道适配、架构、开发与错误码 | [apps/connector-zentao](../apps/connector-zentao/) |

## 公共开发规范

- [领域文档](agents/domain.md)
- [问题跟踪](agents/issue-tracker.md)
- [分诊标签](agents/triage-labels.md)

项目文档中的开发命令和源码相对路径默认以对应 `apps/<项目>/` 为工作目录；平台部署指南的命令在仓库根目录执行。明确以 `docs/`、`apps/`、`scripts/` 开头的路径均相对仓库根目录。历史设计和验证记录保留原时间语境及未纳入仓库的本机截图路径，不代表当前部署状态。
