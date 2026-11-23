# api-ui-worker 开发指引

> 状态：现行｜负责人：api-ui-worker maintainer｜最近复核：2026-11-19｜复核周期：每季度
>
> 适用范围：`apps/api-ui-worker/`。变更/废弃：按[规范变更检查清单](../../docs/agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

遵循根目录 [AGENTS.md](../../AGENTS.md)。开发或审查本项目代码、任务协议及执行流程前，阅读[通用后端规则](../../docs/agents/backend-development.md)、[项目开发规则](../../docs/api-ui-worker/development-rules.md)和[项目说明](../../docs/api-ui-worker/README.md)，按变更类型选择验证入口。

本项目独立执行 API 与 UI 自动化，业务数据与权限通过控制面协议管理。保留现有线程委托、队列公平性、文件授权及停止契约，不直接访问控制面数据库。

持续维护文档放在 `docs/api-ui-worker/`；进行中的规格和工单放在仓库根目录 `.scratch/`，需要长期追溯的规格及验收证据按[长期记录规则](../../docs/records/README.md)提升到项目 records 目录。依赖、锁文件、Dockerfile 与启动入口保持独立。
