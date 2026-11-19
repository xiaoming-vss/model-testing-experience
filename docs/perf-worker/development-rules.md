# 性能 Worker 开发规则

- 状态：现行
- 负责人：perf-worker maintainer
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：`apps/perf-worker/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

开发和审查 `apps/perf-worker/` 前，必须阅读[通用后端规则](../agents/backend-development.md)和[项目说明](README.md)。本文件补充性能执行、数据参数化和进程管理的约束，源码和命令默认相对该应用目录。

## 模块与运行边界

- 沿用本项目 Python 3.12、独立依赖、锁文件、Dockerfile 和启动入口；k6 版本在镜像和配置中锁定。
- `contracts/` 维护严格 RunSpec、Worker 协议与结果契约；`compiler/` 只做校验、归一化和执行计划生成；`runner/` 管理 k6 子进程；`control_plane/` 只封装内部 HTTP 协议；`worker/` 负责领取、租约、心跳、停止和健康文件。
- Worker 不直接访问控制面数据库；通过 `/internal/perf-worker` 领取任务、读取冻结快照和数据文件、回传结果。
- 一个 Worker 同时只执行一个 k6 任务；扩容通过增加 Worker 实例完成。
- 不在 API/UI Worker 中复用本项目代码，也不把浏览器/API 功能测试执行器引入本项目。

## 契约与校验

- Pydantic 模型使用 `extra="forbid"` 和 camelCase alias；未知字段必须拒绝。
- `specVersion` 只接受已声明版本；新增版本时同步更新编译器和模板版本。
- 负载模型只允许 `vus`、`arrival_rate`、`request_rate`、`staged_vus` 之一；`request_rate` 只支持单步骤迭代。`staged_vus` 按 `stages[{target, ramp, hold}]` 编译为 `ramping-vus`，`profile` 仅作展示元数据，不参与执行。
- 验收标准来源为 `user_confirmed | model_suggested | missing`；模型建议不能 `confirmed=true`，缺少标准时不能携带 criteria。
- 模板引用在编译期静态校验：数据列、已提取变量、环境变量和内置生成器之外的占位符一律拒绝。
- 数据文件必须位于运行规格目录内；拒绝路径穿越、重复列名、空数据和超过上限的文件。
- YAML 使用安全解析并拒绝重复键；JSON 同样拒绝重复键。模板占位符、时长和版本号必须显式加引号。

## 安全与日志

- 环境变量值、数据内容和 Remote Write 凭据不写入 `plan.json`、summary、日志或回传结果。
- k6 子进程使用最小化环境：只传入 `PATH`、`HOME`、`PWD`、`TMPDIR`、`K6_PROMETHEUS_RW_*` 和用例引用的环境变量；不透传 Worker 自身的控制面令牌。
- 日志只记录运行标识、状态、退出码、耗时和安全错误；不记录请求体、响应体、数据行或凭据。
- 运行工作目录 0700，冻结规格、计划和数据文件 0600；当前保留供排查，自动保留/清理策略尚未实现。
- 生成脚本只来自固定模板，不允许用户直接提交 JS 或任意表达式。
- 控制面令牌只放在 HTTP 请求头，不写入日志、k6 环境或运行工作区；数据文件从控制面流式下载，Worker 不持有 S3 凭据。
- 控制面错误只记录状态码和任务 ID，不记录响应体、令牌、签名 URL 或运行秘密。

## 执行语义

- k6 通过 `asyncio.create_subprocess_exec(..., start_new_session=True)` 运行，停止时向整个进程组发送 `SIGINT`，宽限期后 `SIGKILL`。
- 退出码 `0` 为执行完成，`99` 为阈值不达标但执行完成，其他非零为执行异常；阈值失败不能当作脚本失败。
- `summary.json` 缺失时标记 `summary_missing`，不能伪造成功或零值。
- 达到最大执行时长时终止进程并标记 `timed_out`；停止结果不能覆盖已完成状态，迟到的成功也不能覆盖停止状态。
- 数据分配策略和用尽策略必须显式：`unique_per_iteration`、`per_vu`、`random`、`cycle`；`onExhausted` 为 `cycle` 或 `fail`。
- 提取变量只在当前 VU 的当前迭代内有效；不实现跨 VU 共享可变状态。

## 控制面 poll 模式

- 租约窗口使用 `time.monotonic`；心跳使用请求开始时间续租，迟到响应不能复活已经过期的租约。
- 一次只领取一个任务；空队列按 `poll_interval_seconds` 等待，SIGTERM/SIGINT 后不再领取新任务。
- 执行前检查 `control` 的 `stopRequested`；执行中由心跳接收停止标志。用户停止、Worker 关闭和租约丢失分别回传不同原因。
- 租约失效或停止请求必须终止整个 k6 进程组；停止后不能把已完成的成功结果改写成停止结果，也不能反过来覆盖停止。
- 数据文件下载先写临时文件，校验大小和 SHA-256 后再原子替换为 0600 目标文件；失败不把半成品交给编译器。
- 完成事件先持久化 `result.json` 再上报；上报失败只在租约内重试上报，不重新执行 k6。终态事件重复上报必须幂等。
- `poll` 缺 `control_plane.base_url` 或专用令牌时必须明确拒绝启动，不能回退到 `once` 或共享 Worker 令牌。

## 验证入口

安装、全量测试、Ruff、格式和 mypy 命令统一见[验证命令矩阵](../commands.md#perf-worker)。

| 变更 | 必跑入口 |
| --- | --- |
| 配置加载与路径 | `tests/test_config.py` |
| RunSpec/结果契约 | `tests/test_contracts.py` |
| 负载映射、数据、占位符 | `tests/test_compiler.py` |
| 固定模板契约 | `tests/test_template_contract.py`、真实 k6 测试 |
| 子进程、停止、超时、脱敏 | `tests/test_k6_runner.py` |
| once 模式与 CLI | `tests/test_once_mode.py` |
| poll 领取、执行、停止 | `tests/test_poller.py` |
| 控制面客户端、下载校验、错误脱敏 | `tests/test_control_plane_client.py` |
| 租约窗口与迟到续租 | `tests/test_worker_lease.py` |
| 健康文件 | `tests/test_health.py` |
| summary 解析 | `tests/test_summary.py` |

真实 k6 测试在没有 `k6` 时跳过；不得把假 k6 测试当作真实压测验收。涉及 Remote Write 的变更应在开启接收能力的 Prometheus 上验证 `run_id` 指标可查。
