# api-ui-worker 开发指引

遵循根目录 [AGENTS.md](../../AGENTS.md)。开发或审查本项目代码、任务协议及执行流程前，阅读[通用后端规则](../../docs/agents/backend-development.md)、[项目开发规则](../../docs/api-ui-worker/development-rules.md)和[项目说明](../../docs/api-ui-worker/README.md)，按变更类型选择验证入口。

本项目独立执行 API 与 UI 自动化，业务数据与权限通过控制面协议管理。保留现有线程委托、队列公平性、文件授权及停止契约，不直接访问控制面数据库。

持续维护文档放在 `docs/api-ui-worker/`，规格和工单放在仓库根目录 `.scratch/`。依赖、锁文件、Dockerfile 与启动入口保持独立。
