# ADR 0032：重放只对原身份幂等

- 状态：已接受
- 日期：2026-11-26
- 取代：—
- 被取代：—
- 关联：[Worker 公共生命周期约定](../../agents/worker-conventions.md)、[开发规则](../development-rules.md)、[禅道 Bug 同步到平台：需求草案](../bug-zentao-reverse-sync-requirements.md)、[ADR 0010](0010-unified-ai-execution.md)

## 背景

Worker 公共约定要求终态回传幂等，但控制面对已结束任务的 `started`、`heartbeat`、`completed` 事件先做执行授权和租约校验、后判断任务状态。用户停止、授权撤销或租约回收之后，原 Worker 迟到的结果或重试会收到 400/403，Worker 无法区分“结果已被接受”和“租约被拒绝”。[ADR 0010](0010-unified-ai-execution.md) 的直接阶段任务只对测试单图谱一种任务类型放行迟到的完成事件，其余任务类型仍会先失败尝试。

禅道 Bug 导入以客户端提供的请求编号做幂等。回放时只按编号查记录并直接返回原 Bug 的编号和标题，没有核对发起的操作者和项目：拿到同一请求编号的其他成员可以读到别的项目的 Bug 信息，违背需求草案 R12。

## 决策

1. 通用队列任务（`services/worker_task.py`）和直接阶段任务（`services/stage_storage/worker_service.py`）处理 `started`、`heartbeat`、`completed` 时，先判断任务是否已进入终态，再做执行人、授权和租约校验。
2. 终态任务的事件只确认或拒绝，绝不应用：
   - `completed`（API/UI 队列任务和全部直接阶段任务）：执行人必须是任务当前记录的 Worker，返回 2xx 和任务当前状态，不重复写结果、不改写 `finished_at` 与尝试状态；其他 Worker 仍返回 403。
   - `heartbeat`：不校验执行人，返回 2xx，不续租、不改写状态。
   - `started`：对任务记录的 Worker 返回 `409`（第 4 条），其他 Worker 返回 403。Worker 此时还没有执行任何步骤，确认会让它继续读取快照并开始执行一个已结束的任务。
   - 请求体 `taskId` 或 `runId` 与任务不一致时仍返回 400。
3. 非终态任务的校验顺序和行为不变。AI 和性能队列任务迟到的 `completed` 不在本次范围内，继续按各自状态机处理。
4. Worker 事件对应的执行已不再有效时（任务不在 `claimed/running/stopping`，或租约已过期），控制面返回 `409` 和错误码 `ErrWorkerLeaseLost`，不再与请求参数错误共用 `400`。Worker 因此只需一个集合 `{401, 403, 404, 409, 410}` 判断“执行已被控制面收回”，把 `400`/`422` 一律当作自己发出的请求有问题。缺少 Worker 身份、身份或运行 ID 不一致、状态值非法仍是 `400`，执行人不匹配仍是 `403`。
5. 领取、授权撤销和租约过期路径只吞掉明确预期的业务错误码；其他业务错误向上抛出，不再用 `except type(错误实例)` 把全部业务错误一并吞掉。
6. Bug 导入回放只对原操作者在原项目返回原结果；其他操作者或项目命中同一请求编号时按 `conflict` 处理并提示更换请求编号，不返回对方 Bug 的编号和标题。

## 后果

- Worker 重试一个已被接受的完成事件得到 2xx，可以停止重试；被新 Worker 接管的任务仍只认当前持有者，旧 Worker 的结果不会覆盖新结果。
- 迟到回传不再把已结束的任务改写成失败，也不再改写完成时间。`canceled` 完成事件与其他终态一样写入 `finished_at`。
- API、UI 和性能运行不记录个人连接依赖：撤销个人连接不终止这些运行，只终止依赖该连接的 AI 运行。恒为空的 `ExecutionAuthority.connection_ids` 及其循环随之删除。
- 第 4 条影响四个 Worker。perf-worker 和 integration-worker 本来就把 `409` 当作失租，无需修改；ai-worker 按本地单调时钟窗口判定失租，不依赖状态码；api-ui-worker 据此把三份互不一致的判定收敛为一个集合。滚动升级时控制面应先于或同批于 api-ui-worker 升级：旧控制面对失效租约仍返回 `400`，新 api-ui-worker 不会立即识别，要等本地租约窗口到期才停止执行。

## 验证

- `tests/test_worker_late_events.py` 覆盖迟到报告的确认、陌生 Worker 拒绝、迟到 `started` 的拒绝、身份不一致拒绝，授权撤销和租约过期只吞掉预期错误，以及失效租约返回 `409`、缺少 Worker 身份仍返回 `400`。
- `tests/test_zentao_bug_import.py` 覆盖回放对操作者和项目的绑定。

## 备选方案

- **保持拒绝，由 Worker 侧自行判断**：Worker 拿不到“已被接受”和“已被拒绝”的区别，重试逻辑只能靠超时收敛，不采用。
- **终态事件对所有 Worker 一律确认**：旧 Worker 无法据此判断自己已失去租约，且掩盖配置错误的 Worker 身份，不采用。
