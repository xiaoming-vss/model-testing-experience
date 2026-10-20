# 领域上下文导航

业务上下文和架构决策统一维护在 `docs/`；本文件只提供阅读入口。

| 项目 | 领域上下文 | 架构决策 / 项目说明 |
| --- | --- | --- |
| 控制面 | [CONTEXT](docs/control-plane/CONTEXT.md) | `docs/control-plane/adr/`、[模块接口与事务责任](docs/control-plane/README.md#模块接口与事务责任)、[整改实施记录](docs/control-plane/remediation-implementation.md) |
| AI Worker | [CONTEXT](docs/ai-worker/CONTEXT.md) | `docs/ai-worker/adr/`、[项目说明](docs/ai-worker/README.md) |
| 前端 | [CONTEXT](docs/studio/CONTEXT.md) | `docs/studio/adr/`、[项目说明](docs/studio/README.md) |
| API/UI Worker | — | [项目说明](docs/api-ui-worker/README.md) |
| 集成 Worker | [CONTEXT](docs/integration-worker/CONTEXT.md) | [项目说明](docs/integration-worker/README.md)、[控制面 ADR 0006](docs/control-plane/adr/0006-independent-integration-execution.md) |

ADR 目录按需创建，不预先建立占位文件；各项目的 ADR 编号相互独立。领域术语和决策的记录规则见 [领域文档规范](docs/agents/domain.md)。

四个后端项目共用[通用后端开发规则](docs/agents/backend-development.md)，各项目补充规则与验证入口由该文档导航；控制面的 Web 和数据库要求仅适用于控制面。
