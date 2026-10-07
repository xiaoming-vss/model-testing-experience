# 集成 Worker 开发规则

开发和审查 `apps/integration-worker/` 前，必须阅读[通用后端规则](../agents/backend-development.md)、[领域上下文](CONTEXT.md)和 [ADR 0006](../control-plane/adr/0006-independent-integration-execution.md)。本文件补充外部写入与证据恢复要求，源码和命令默认相对该应用目录。

## 模块与依赖

沿用本项目 Python 3.12 与独立运行环境。`main/app` 负责入口和装配，`worker/` 管理领取、租约及停止，`handlers/` 分派任务，`services/` 编排步骤，`repositories/` 访问控制面 HTTP，`gateways/` 访问 MCP，`domain/` 保存纯规则，`schemas/` 限制协议载荷。

业务服务必须显式接收依赖，不能直接创建第二套控制面或 MCP 客户端。Worker 不安装控制面 ORM、数据库或 Web 框架，不持有数据库连接、长期 S3 密钥或公开业务端口。不能把本项目的 HTTP repository 误解为控制面的数据库 repository。

## 一次写入与未知结果

每次外部写入必须取得控制面已持久化、绑定当前任务、步骤、operation 和领取代次的许可。控制面请求重试复用原 claim/prepare/result 身份；MCP 写调用只执行一次。准备响应丢失后查询原意图，不能把查询结果当成新写许可。

失租、许可到期和停止后不开始新写入，在途调用保留明确结果或 unknown。结果回传失败使用安全证据路径恢复，不重新发起 MCP 写入。源码重启、容器重建和数据库恢复均不能把未知操作当成未执行。

凭据、签名 URL 和访问材料仅驻内存。本地结果日志只保存 Schema 限定的原操作身份及安全结果，禁止保存原始错误、冻结输入或自行改写旧事件以适配新版本。恢复日志的权限、每副本隔离、排空及归档按[运维说明](README.md#停止与结果日志)执行。

## 验证入口

本项目已经在 `pyproject.toml` 固定 mypy 的 `src` 范围、函数体检查和无用忽略检查，继续使用项目配置。

```sh
uv sync --locked --extra dev
uv run --locked --extra dev python -m pytest
uv run --locked --extra dev ruff check .
uv run --locked --extra dev ruff format --check <修改的源码及测试路径>
uv run --locked --extra dev mypy
```

| 变更 | 必跑入口 |
| --- | --- |
| 领取、回传与协议兼容 | `tests/test_worker_protocol.py`，加控制面队列及内部协议专项 |
| 租约、许可、心跳与停止 | `tests/test_worker_lease.py`，加对应跨进程工作流 |
| MCP 调用与写后核对 | `tests/test_zentao_gateway.py`，加实际工具输入和安全结果回归 |
| 配置与运行代次 | `tests/test_config.py`，跨部署修改追加根目录编排检查 |
| 未知结果与证据恢复 | `tests/integration/test_sync_recovery.py`，加控制面的恢复、隔离和 `test_integration_jobs_mysql.py` |
| 长传输或排空边界 | 显式运行 `tests/integration/test_long_upload.py`；开关和隔离依赖见[项目说明](README.md#检查) |

跨进程检查安装隔离 fixture 所需的控制面开发依赖，不访问当前运行服务。真实 MySQL、禅道、S3 和部署切换分别验收，fixture 通过不能代替真实写入或恢复证据。测试也必须遵守一次写入及凭据安全边界。
