# ADR 0002：性能任务接入控制面与 poll 模式

> 2026-11-17：监控接入已收敛为 Prometheus Remote Write only，查询凭据与 Grafana 配置由控制面 [ADR 0020](../../control-plane/adr/0020-performance-remote-write-only.md) 移除；本文中相关的历史描述以该决策为准。

- 状态：已采纳
- 日期：2026-11-16

## 背景

ADR 0001 已把性能执行独立到 `apps/perf-worker`，但首期只有本地 `once` 模式，用例、监控接入和运行记录都没有进入控制面。平台需要形成“创建运行 → Worker 拉取 → k6 执行 → 结果回传”的闭环，同时保持压测执行与 API/UI 功能执行隔离。

约束：

- 性能运行可能持续数十分钟到数小时，Worker 必须可独立部署和扩容，不能与控制面或 API/UI Worker 共用进程。
- k6 指标通过 Remote Write 写入项目选择的 Prometheus；Grafana 只供人查看，平台不部署采集组件。
- CSV/JSON 数据文件可能达到数十 MB，不能写入 MySQL 行内字段。
- 当前队列已有 `worker_tasks` 的领取、心跳、租约和回收机制，不需要为性能任务复制一套独立账本。

## 决策

1. **复用 `worker_tasks`，新增 `domain="perf"`**。性能任务使用独立 60 秒租约、10 秒心跳和 `task_type="perf_run"`；不新建 integration 式队列。领取仍在数据库中使用 `SKIP LOCKED`，Worker 一次只执行一个任务。
2. **独立 `perf_worker_token`**。控制面新增 `[security.perf_worker].key`，性能 Worker 使用自己的令牌调用 `/internal/perf-worker`；该令牌必须与 AI/API/UI 和 integration Worker 令牌不同。
3. **控制面拥有用例、运行和监控接入**。`perf_cases` 保存可编辑 YAML 和版本；`perf_runs` 冻结发起时的用例 YAML、RunSpec、数据文件元数据、环境和监控接入名称；`monitoring_connections` 保存项目级 Prometheus/Grafana 连接及加密凭据。
4. **RunSpec 在控制面组装并冻结**。运行创建时校验项目权限、环境 `kind="perf"`、监控接入和附加数据文件，合并环境变量和 Remote Write 凭据，生成完整 RunSpec。公开 `spec_json` 脱敏；完整规格和秘密写在 `private_payload` 中，使用现有 `IntegrationCredentialCipher` 加密，仅当前租约持有者可读取快照。
5. **CSV/JSON 走现有 S3 `stored_files`**。新增 `purpose="perf_case_data"`，对象目录 `perf-case-data`，只允许 CSV/JSON、单文件上限 50 MiB。运行冻结文件元数据，历史文件保持在原用例关联下。Worker 不持有 S3 凭据：控制面校验运行快照中的文件 ID、大小和 SHA-256 后，将对象流式返回给 Worker；Worker 再次校验大小和哈希。
6. **Worker 新增 `poll` 模式**。启动后按 `poll_interval_seconds`（默认 2 秒）领取任务；通过 heartbeat 续租并接收停止标志；租约失效立即停止 k6；SIGTERM/SIGINT 停止领取并让当前 k6 在宽限期内退出。完成结果先写本地 `result.json`，再上报控制面；上报失败在租约内重试，不重跑 k6。
7. **本期不引入 Redis 唤醒和 SSE**。2 秒轮询加心跳停止已满足执行闭环；Redis 仅作为后续降低领取延迟的优化，不改变协议。控制面本期也不实现 Prometheus 查询、Grafana 链接渲染和 AI 生成/分析。
8. **Compose 纳入 perf-worker，Helm 暂不纳入**。Compose 使用独立生成配置、专用令牌和匿名 `/app/runtime` 卷；一个副本同时只执行一个 k6 任务，扩容通过增加实例完成。Helm chart 留到后续阶段。

## 状态映射

Worker 只回传执行事实，控制面负责运行生命周期：

| Worker 结果 | `perf_runs.status` | `worker_tasks.status` |
| --- | --- | --- |
| `completed` + `passed/threshold_failed/inconclusive` | `completed` | `success` |
| `failed` | `failed` | `failed` |
| `stopped` | `stopped` | `canceled` |
| `canceled` | `canceled` | `canceled` |

用户停止时任务先进入 `stopping`；Worker 收到停止标志后终止 k6 并回传 `canceled`。若在停止后收到迟到的成功结果，控制面强制记为 `canceled/stopped`，不能覆盖停止。心跳超时由现有租约回收器将运行置为 `failed/execution_error`。

## 后果

- 性能任务与 AI/API/UI 共享 `worker_tasks` 和租约回收机制，减少重复状态机；代价是查询和索引需要按 `domain` 区分，性能队列的延迟由轮询周期决定。
- 数据文件不进入 MySQL，控制面需要为每次 Worker 下载承担一次对象读取流量；Worker 不需要对象存储网络和凭据，部署更简单。
- 运行快照包含秘密，必须保证 `private_payload` 加密、快照接口只对当前租约持有者开放、公开规格和日志再次脱敏。
- 旧数据文件随用例历史保守保留；替换数据文件不会使历史运行失效。本期不自动回收已替换的正式文件，沿用统一存储的保留策略。
- 完整运行产物（plan/main.js/k6.log）暂不上传 S3；MySQL 只保存有上限的 summary（5 MB）和日志尾部（16 KB）。
- 当前一个 Worker 一个任务；高并发压测需要更多 Worker 实例或后续增加受控并发度。
