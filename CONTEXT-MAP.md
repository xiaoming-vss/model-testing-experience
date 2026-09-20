# 领域上下文导航

业务上下文和架构决策统一维护在 `docs/`；本文件只提供阅读入口。

| 项目 | 领域上下文 | 架构决策 / 项目说明 |
| --- | --- | --- |
| 控制面 | [CONTEXT](docs/control-plane/CONTEXT.md) | `docs/control-plane/adr/`、[项目说明](docs/control-plane/README.md) |
| AI Worker | [CONTEXT](docs/ai-worker/CONTEXT.md) | `docs/ai-worker/adr/`、[项目说明](docs/ai-worker/README.md) |
| 前端 | [CONTEXT](docs/studio/CONTEXT.md) | `docs/studio/adr/`、[项目说明](docs/studio/README.md) |
| API/UI Worker | — | [项目说明](docs/api-ui-worker/README.md) |
| 禅道适配 | — | [架构说明](docs/connector-zentao/architecture.md)、[项目说明](docs/connector-zentao/README.md) |

ADR 目录按需创建，不预先建立占位文件；各项目的 ADR 编号相互独立。领域术语和决策的记录规则见 [领域文档规范](docs/agents/domain.md)。
