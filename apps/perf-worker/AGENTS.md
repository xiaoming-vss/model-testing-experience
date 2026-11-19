# perf-worker 开发指引

> 状态：现行｜负责人：perf-worker maintainer｜最近复核：2026-11-19｜复核周期：每季度
>
> 适用范围：`apps/perf-worker/`。变更/废弃：按[规范变更检查清单](../../docs/agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

遵循根目录 [AGENTS.md](../../AGENTS.md)。开发或审查本项目代码、执行协议与运行流程前，阅读[通用后端规则](../../docs/agents/backend-development.md)、[项目开发规则](../../docs/perf-worker/development-rules.md)和[项目说明](../../docs/perf-worker/README.md)，按变更类型选择验证入口。

本项目独立执行性能测试：通过控制面 `poll` 模式领取性能运行，或读取本地运行规格，使用固定 k6 模板和数据文件驱动 k6，将指标写入 Prometheus，并回传执行结果。Worker 不直接访问控制面数据库；数据文件由控制面流式下发，Worker 不持有 S3 凭据。保留独立依赖、锁文件、Dockerfile 与启动入口。

持续维护文档放在 `docs/perf-worker/`，规格和工单放在仓库根目录 `.scratch/`。
