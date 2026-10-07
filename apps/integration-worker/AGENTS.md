# integration-worker 开发指引

遵循根目录 [AGENTS.md](../../AGENTS.md)。先读 [领域上下文](../../docs/integration-worker/CONTEXT.md)及[执行决策](../../docs/control-plane/adr/0006-independent-integration-execution.md)；配置、协议、恢复及目录职责见[项目说明](../../docs/integration-worker/README.md)。

开发或审查代码、写入协议及恢复流程前，阅读并遵循[通用后端规则](../../docs/agents/backend-development.md)和[集成 Worker 开发规则](../../docs/integration-worker/development-rules.md)，按变更类型选择验证入口。

`main.py` 处理 CLI，`app.py` 集中装配依赖；`worker/` 管理领取、租约与停止，`handlers/` 分派任务，`services/` 编排步骤，`repositories/` 访问控制面 HTTP，`gateways/` 访问 MCP，`domain/` 保存无 I/O 规则，`schemas/` 校验协议。业务服务显式接收依赖，依赖方向指向外部访问与规则层；运行时独立于控制面 ORM、数据库与 Web 框架。

每次写入先取得控制面已持久化的步骤许可。失租和 SIGTERM 停止新写入；在途请求按未知结果或受限证据处理。网络重试仅复用控制面请求/事件编号，MCP 写入执行一次。凭据与签名 URL 仅驻内存；本地恢复日志只能保存经过 schema 限制的原操作身份和安全结果。

修改后运行 `uv run --extra dev python -m pytest`、`uv run --extra dev ruff check .`、`uv run --extra dev mypy`。跨进程 fixture 和失租恢复检查与单元测试并用；共享编排修改另执行根目录规定的检查。
