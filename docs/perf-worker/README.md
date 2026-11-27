# 性能 Worker（perf-worker）

`apps/perf-worker` 是独立的性能测试执行 Worker：读取运行规格，使用固定 k6 模板驱动 k6，把指标通过 Remote Write 写入 Prometheus，并回传执行结果。

支持两种运行模式：

- **`poll`（控制面接入）**：通过 `/internal/perf-worker` 领取性能运行，下载冻结的数据文件，执行后回传结果；Compose 已纳入该模式。
- **`once`（本地排查）**：直接读取一份 RunSpec（YAML 或 JSON），不连接控制面。

决策记录见 [ADR 0001](adr/0001-independent-perf-worker.md)、[ADR 0002](adr/0002-control-plane-poll-mode.md) 和 [ADR 0003](adr/0003-performance-run-metrics-context.md)；[性能运行指标规格](records/2026-11-20-performance-metrics-spec.md)记录本次实施范围。

外部夜莺看板查询参考[夜莺性能运行查询](nightingale-dashboard.md)；中文名称映射仍待实现。
本地隔离验证范围见[性能运行指标阶段验证](records/2026-11-20-performance-metrics-validation.md)。

首次公开发布前，新增运行迭代字段已写入唯一 Alembic baseline。已经执行过该 baseline 的开发数据库不会因重复执行 `alembic upgrade head` 自动获得新列；应先备份并确认本地库版本，在停机状态下按预发布本地库维护流程补齐 `perf_runs` 和 `perf_suite_runs` 的可空 `sprint_id VARCHAR(64)`、非空且默认为空字符串的 `sprint_name VARCHAR(100)`，并核对中文列注释与 baseline 一致。不得直接在生产库执行未经验证的 DDL。

## 执行链路

```text
控制面 perf_run
  → Worker claim → snapshot（完整 RunSpec + 数据文件元数据）
  → 控制面流式下发 CSV/JSON，Worker 校验大小与 SHA-256
  → Python 编译器校验并生成 plan.json + main.js + data/*.json
  → k6 子进程读取 plan.json
  → Remote Write 写入所选 Prometheus
  → summary.json + result.json
  → Worker 回传完成事件
```

本地 `once` 跳过前两步，直接从 RunSpec 开始。两种模式复用同一编译器、固定模板、k6 进程管理和结果契约。

- 用例的 YAML 是唯一可编辑来源；`plan.json` 是派生执行产物，不作为第二份手写格式。
- `main.js` 是固定模板，按 `plan.json` 循环执行步骤、校验、提取和取数；不为每个用例生成 JS。
- 环境变量值只通过最小化子进程环境传给 k6，不写入 `plan.json`、日志或回传结果。
- CSV 由 Python 解析为 `data/<name>.json`，k6 用 `SharedArray` 读取；数据文件只在运行工作区存在。

## 配置

```sh
cd apps/perf-worker
uv sync --locked --extra dev
cp config/local.example.toml config/local.toml
# poll 模式：填写 [control_plane].base_url 和 worker_token
uv run --locked mtx-perf-worker --config config/local.toml

# once 模式：设置 mode = "once" 并编辑 [once].snapshot_file
uv run --locked mtx-perf-worker --config config/local.toml
```

配置优先级：`--config` > `APP_CONF` > `./config/local.toml`。相对运行路径按当前工作目录解析。生产配置由仓库根目录的 `scripts/manage.py` 从 `config/platform.toml` 生成，使用独立的 `shared.perf_worker_token`，不要提交 `config/local.toml`。

镜像内固定 k6 `2.3.0`；配置模型默认和示例均使用同一版本。`poll` 模式在领取任务前校验版本，每次执行前再次校验；`once` 模式在执行前校验。版本不匹配时 Worker 明确失败，不回退到未验证的 k6 二进制。

关键配置：

| 配置 | 作用 |
| --- | --- |
| `mode` | `poll`（控制面领取）或 `once`（本地规格） |
| `[control_plane].base_url` | 控制面地址；`poll` 模式必填 |
| `[control_plane].worker_token` | 性能 Worker 专属令牌；`poll` 模式必填 |
| `[control_plane].timeout_seconds` / `retry_attempts` | HTTP 超时和 5xx/429 重试次数 |
| `[worker].poll_interval_seconds` | 空队列轮询间隔，默认 2 秒 |
| `[worker].heartbeat_interval_seconds` | 租约心跳间隔，默认 10 秒 |
| `[worker].lease_margin_seconds` | 本地判定租约失效的提前量 |
| `[worker].shutdown_grace_seconds` | SIGTERM 后停止领取并等待当前运行退出的时间；超过后取消仍在执行的运行 |
| `[k6].binary` | k6 可执行文件，默认 `k6` |
| `[k6].expected_version` | 期望的 k6 版本；默认和各环境示例为 `2.3.0`，poll 启动和每次执行前校验，不匹配明确失败 |
| `[runner].workspace_root` | 每次运行的独立工作目录根 |
| `[runner].max_duration_seconds` | Worker 兜底执行时长 |
| `[runner].stop_grace_seconds` | SIGINT 后的优雅停止宽限期 |
| `[runner].max_data_file_mb` | CSV/JSON 数据文件上限 |
| `[runner].max_summary_mb` | summary 读取上限，默认 5，须与控制面的拒绝上限一致；超限时标记 `summary_missing` 并在 `errorMessage` 说明原因 |
| `[once].snapshot_file` | 本地运行规格路径，仅 `once` 模式必填 |

## 控制面 poll 模式

Worker 使用异步 HTTP 客户端访问 `/internal/perf-worker`，请求头带 `X-Worker-Token`。协议顺序：

```text
POST /tasks/claim                         无任务 204；有任务返回 taskId/runId/leaseSeconds
GET  /tasks/{taskId}/snapshot             完整 RunSpec（含运行秘密）+ 数据文件元数据
GET  /tasks/{taskId}/control              执行前兜底检查 stopRequested
POST /tasks/{taskId}/started              运行置 running
POST /tasks/{taskId}/heartbeat            续租并接收 stopRequested
GET  /tasks/{taskId}/data-files/{fileId}  控制面从 S3 流式返回文件
POST /tasks/{taskId}/completed            回传状态、outcome、summary、日志尾部等
```

- 一次只领取一个任务；空队列等待 `poll_interval_seconds`，处理 SIGTERM/SIGINT 时不领取新任务。
- 本地租约窗口基于 `time.monotonic`，迟到的心跳不能复活已经过期的租约；租约失效立即停止 k6。
- 心跳返回 `stopRequested` 后停止 k6：用户停止回传 `canceled`，Worker 关闭回传 `stopped`，租约丢失回传 `stopped`。`once` 模式收到取消或 `KeyboardInterrupt` 时同样终止整个 k6 进程组并等待退出。停止原因到结果的映射只在一处定义（`worker/poller.py` 的 `_STOP_RESULTS`）。
- k6 启动前控制面明确拒绝租约（快照、控制查询、开始上报）时 Worker 不合成结果，由控制面按租约回收结束尝试；同一阶段的其他控制面错误和不符合协议的快照按 `failed/execution_error` 上报，不让一次坏快照中断轮询。
- 健康文件按「临时文件 + 原子替换」写入，探针读不到半写入内容；轮询退出（含 `once` 模式）时删除文件。
- 数据文件在写入前校验大小和 SHA-256，文件名拒绝路径分隔符；文件落在运行目录 `inputs/`（0700），文件权限 0600。下载遇到 429/5xx 按 `retry_attempts` 退避重试，其他 4xx 立即失败。
- 完成结果先写 `result.json` 再上传；上报失败在同一租约窗口内按 0.5s 起指数退避（上限 5s）重试，租约到期后停止并保留 `result.json`，不重新运行 k6。控制面明确拒绝租约（`LeaseLostError`）时立即停止重试，日志带状态码，便于区分令牌配置错误和载荷超限。控制面对终态完成事件幂等，重复上报携带同一结果，不产生第二次运行。

完整的领取、租约、停止和幂等语义见 [ADR 0002](adr/0002-control-plane-poll-mode.md)。

## 运行规格

参考 [tests/fixtures/case.yaml](../../apps/perf-worker/tests/fixtures/case.yaml) 和 [snapshot.json](../../apps/perf-worker/tests/fixtures/snapshot.json)。要点：

- `specVersion` 当前支持 `"1.0"`，必须显式加引号。
- `load.model` 只允许 `vus`、`arrival_rate`、`request_rate`、`staged_vus` 之一；`request_rate` 只支持单步骤迭代。
- `staged_vus` 使用 `stages` 列表（`target`、`ramp`、`hold`）和可选 `finalDown` 编译为 k6 `ramping-vus`；`profile` 仅为模板标记，不参与执行。
- `acceptance.source` 为 `user_confirmed | model_suggested | missing`；模型建议不能标记 `confirmed=true`。
- `data` 支持 `source` 文件或内联 `rows`；列名跨数据集必须唯一。
- 模板占位符支持 `{{data.x}}`、`{{var.x}}`、`{{env.x}}` 以及 `{{uuid}}`、`{{timestamp}}`、`{{iteration}}`、`{{vu}}`。
- 步骤的 `expectedStatuses` 可列出可接受的 HTTP 状态码；省略时接受 2xx。按请求状态、响应检查、变量提取的顺序判定，第一个失败阶段决定失败原因。
- 运行规格可选 `projectId`、`sprintId`、`suiteId`、`suiteRunId` 和 `caseId`；非空身份随 `run_id` 加入指标标签。
- 环境变量名不能以 `K6_` 开头，也不能使用 `PATH`、`HOME` 等保留名。

## 执行结果

`result.json` 与标准输出包含：

- `status`：`completed`、`failed`、`stopped`、`canceled`
- `outcome`：`passed`、`threshold_failed`、`inconclusive`、`execution_error`、`stopped`
- `exitCode`、时间、k6 版本、模板版本、脚本 SHA-256
- `summary`：从 `summary.json` 提取的指标与阈值结果
- `flags`：`summary_missing`、`log_truncated`、`remote_write_error`。其中 `remote_write_error` 表示从 k6 输出中观察到 Remote Write 失败；没有该标志不能证明监控已成功接收。`summary_missing` 也用于无法读取、超过上限或不是 JSON 对象的摘要，此时 `errorMessage` 给出原因。
- `logTail`：脱敏后的日志尾部
- `runner`：主机名、CPU 数量和 k6 版本

k6 退出码语义：`0` 执行完成，`99` 阈值不达标但执行完成，其他非零为执行异常。Worker 只回传事实；最终达标判定、目标负载未达和监控数据缺失由平台判定。

## 命令与验证

测试、Ruff、格式和 mypy 命令统一见[命令矩阵](../commands.md#perf-worker)；按变更类型选择的专项入口见[开发规则](development-rules.md#验证入口)。

有 `k6` 时测试会跑真实模板链路；没有 `k6` 时相关测试跳过。Remote Write 需要 Prometheus 开启接收能力（如 `--web.enable-remote-write-receiver`）。

## 当前限制

- 已接入控制面 poll 模式和 Compose；Helm chart 和 K8s 部署尚未提供。
- 一个 Worker 同时只执行一个 k6 任务；压测并发通过增加 Worker 实例完成。
- 不引入 Redis 唤醒，领取延迟由 2 秒轮询决定。
- 步骤按线性顺序执行，不支持任意条件分支和循环。
- `request_rate` 只支持单请求迭代；多步骤流程使用 `arrival_rate` 或 `vus`。
- 大文件数据整体加载到内存，受 `max_data_file_mb` 和行数上限约束。
- 每次运行保留工作目录便于排查；自动保留/清理策略尚未实现。
- 完整运行产物不上传 S3，控制面只保存 summary 和日志尾部。
