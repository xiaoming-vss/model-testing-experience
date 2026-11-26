# Worker 公共生命周期约定

- 状态：现行
- 负责人：worker maintainers
- 最近复核：2026-11-26
- 复核周期：每季度
- 适用范围：`ai-worker`、`api-ui-worker`、`integration-worker`、`perf-worker`
- 变更/废弃：按[规范变更检查清单](domain.md#规范变更检查清单)执行；影响控制面协议时先记录 ADR 并通知消费方。

四个 Worker 保持独立依赖、独立进程和各自协议，不建立跨应用运行时库，也不要求统一目录结构。本约定只固定健康检查、心跳、租约、回传失败、关闭状态和快照身份的公共语义；具体状态词汇、负载结构和恢复介质仍由各项目协议决定。规则依据见[通用后端开发规则](backend-development.md)。

## 健康检查

健康检查只表示进程和主循环存活，不探测控制面、MCP、S3、浏览器、LLM 或 k6。依赖短暂不可用不能让容器探针失败并触发重启。

| 项目 | 健康检查面 | 必须保持的行为 |
| --- | --- | --- |
| ai-worker | HTTP `GET /healthz` | 返回 200 `ok\n`；其他路径 404；不记录探针访问日志；未设置端口环境变量时不启动服务；非法或越界端口回退 8080 |
| api-ui-worker | HTTP `GET /healthz` | 同 ai-worker；只有端口环境变量名不同 |
| integration-worker | 健康文件 + `--healthcheck` | 文件原子写入 `pid` 和 `progressAt`；进程不存在、文件不可读或超过最大年龄即不健康；健康检查命令成功退出 0、失败退出 1；停止时删除文件 |
| perf-worker | 健康文件 + `--healthcheck` | 同 integration-worker；文件额外记录 `stage` 供排障，不参与健康判定 |

HTTP 服务的启动/停止必须幂等，停止时关闭监听并回收线程。健康文件必须经历临时文件加原子替换，不能让探针读到半写入内容。部署探针的超时和周期应短于文件最大年龄，否则会把仍在运行的 Worker 判为不健康。

## 心跳与租约

1. 领取任务后，必须按领取响应中的租约秒数建立本地窗口，并以 `time.monotonic` 判断截止；不得使用墙上时钟计算剩余时间。
2. 心跳成功才续租；心跳间隔必须小于租约。明确拒绝（控制面返回执行已失效）或窗口到期后，不得开始新的模型调用、API/UI 外部请求、k6 运行或 MCP 写入。
3. 传输错误只在本地窗口内重试；窗口到期即视为租约丢失。迟到的心跳响应不能复活已经过期的窗口。
4. 租约丢失后不得把已完成的执行结果当作成功提交。按协议可提交 `stopped`/`unknown`，或交由控制面租约回收结束尝试；不得合成新的执行结果。
5. 在途操作按项目执行模型清理：AI 在下一个进度检查点停止，API/UI 取消在途协程，perf 终止 k6 进程组，integration 只保留显式结果或 unknown。

| 项目 | 续租与失败处理 |
| --- | --- |
| ai-worker | 间隔取配置值与租约一半的较小者；窗口从续租请求发出时起算，心跳或进度成功都算续租；连续 3 次心跳失败、窗口到期，或控制面以 `401/403/404/409/410` 拒绝开始、心跳或进度即失效；续租类请求的超时不超过剩余租约的一半 |
| api-ui-worker | 按配置间隔心跳；明确拒绝立即过期，普通网络错误由本地截止窗口兜底；领取租约缺失时使用 30 秒默认值。控制面拒绝执行的判定只在 `control_plane/client.py` 定义一处 |
| integration-worker | 间隔取配置值与租约三分之一较小者；心跳响应按请求开始时间续租；控制面错误立即标记租约丢失 |
| perf-worker | 间隔取配置值与租约三分之一较小者；心跳响应按请求开始时间续租；迟到成功不能延长已过期窗口 |

## 回传失败与恢复

执行失败、回传失败、取消和未知结果是不同事实。回传或完成上报失败不得重新执行任务，也不得自动重新调用模型、浏览器、k6 或 MCP 写入。

| 项目 | 回传失败处理 |
| --- | --- |
| ai-worker | 最终结果写入本地 outbox；只在原租约内重试提交；过期条目保留 7 天供诊断，不再投递 |
| api-ui-worker | 抛 `ReportDeliveryError`，只记录安全错误并保留本地产物；不再提交 `status=error` 的执行结果 |
| integration-worker | 使用受限 evidence 日志恢复原事件；未知写入不重新执行，恢复依据是控制面写意图而非本地日志 |
| perf-worker | 先把结果写入 `result.json`，再在租约剩余时间内按退避重试完成上报；重复上报使用相同载荷；租约到期保留本地结果 |

所有重试必须复用原任务、尝试、操作和事件身份。终态回传应幂等；控制面已经拒绝的尝试不再重试。

## 关闭与状态映射

关闭和租约丢失不能报成执行 `error`。各项目状态词汇不同，映射如下：

| 项目 | 用户停止 | Worker 关闭 | 租约丢失 | 回传失败 |
| --- | --- | --- | --- | --- |
| ai-worker | 不接受停止信号，不产生 `canceled` | SIGINT：停止领取新任务并等待在途任务完成；SIGTERM：立即终止模型子进程并退出进程，在途尝试由控制面回收 | 丢弃迟到结果，不提交完成 | 本地 outbox，不重跑模型 |
| api-ui-worker | 回传 `canceled` | 回传 `canceled`；控制面没有 `stopped` | 不合成结果，交由控制面回收 | `ReportDeliveryError`，不提交错误结果 |
| integration-worker | 不开始新写入；在途写入保留显式结果或 unknown | 同左；已开始的写入不得假定未执行 | 可回传 `unknown` 与 `lease_lost`，不重写 | evidence 日志恢复，不重新写 |
| perf-worker | `canceled` | `stopped` | `stopped`，并终止 k6 进程组 | 保留 `result.json`，租约内重试 |

状态词汇按协议固定：ai-worker 使用 `success`、`failed`、`error`，`canceled` 仅为协议兼容保留且 Worker 不发布；api-ui-worker 的执行错误只使用 `error`、`canceled`；integration-worker 的步骤事件只使用 `succeeded`、`failed`、`unknown`；perf-worker 使用 `completed`、`failed`、`stopped`、`canceled`。

## 失败文案

回传给用户的失败原因只有两类。代码里写好的固定文案（可以带阶段、字段、平台编号和数量）原样回传；其余异常一律回传固定提示，日志只记录异常类型和安全栈帧。模型输出、第三方异常文本、请求地址和响应体不得拼进回传文案；说明校验失败时只给出位置和规则，不引用被拒绝的内容本身。

api-ui-worker 是明确的例外：它的失败原因本身就是浏览器和 HTTP 的排障信息，步骤级和任务级都回传执行器异常的文本（定位器、超时、浏览器环境）。它的约束是日志：轮询层遇到未知异常只记录异常类型，控制面错误只记录 `ControlPlaneRequestError` 的固定消息。

| 项目 | 已知失败的承载方式 |
| --- | --- |
| ai-worker | `SafeMessageError` 家族（`UserFacingError`、`AgentOutputError`），由 runner 原样回传；两个模型适配器对非正常结束一律抛 `AgentOutputError`，成功返回的结果视为完整 |
| api-ui-worker | 步骤级和任务级回传执行器异常的文本；轮询层日志对未知异常只记类型 |
| integration-worker | 步骤状态和 `error_code` 是固定词表；未知异常只记类型和安全栈帧 |
| perf-worker | 结果只带 Worker 自己错误类型给出的固定文案；控制面错误只记录状态码和任务 ID |

## 快照与身份字段

Worker 必须把控制面快照视为只读冻结输入，不得自行补造任务归属、修改租约或把缺失字段解释成另一种状态。领取、心跳、开始、完成和恢复事件必须沿用同一任务身份。

| 项目 | 公共身份与租约字段 | 项目特有字段 |
| --- | --- | --- |
| ai-worker | `taskId`、`workerId`、`leaseSeconds` | `attemptId`、`generateTaskId`、阶段与 checkpoint |
| api-ui-worker | `taskId`、`workerId`、`leaseSeconds` | `stopRequested`、case/suite 快照、产物引用 |
| integration-worker | `jobId`、`workerId`、`claimGeneration`、`runtimeGeneration`、`leaseSeconds` | 步骤、operation、输入/目标修订、写许可 |
| perf-worker | `taskId`、`workerId`、`leaseSeconds` | `runId`、`stopRequested`、RunSpec 与数据文件引用 |

线上字段使用 camelCase；使用 Pydantic alias 的项目必须同时接受已声明的 camelCase 和 snake_case 读取别名。新增或删除公共身份字段按[响应字段兼容检查清单](api-change-checklist.md)核对控制面和消费方。

## 允许的项目差异

| 差异 | 项目 | 理由 |
| --- | --- | --- |
| HTTP 探针与健康文件 | ai/api-ui 用 HTTP，integration/perf 用文件 | 前者是长期服务并暴露探针端口；后两者没有公开业务端口，文件检查由容器命令执行 |
| 并发模型 | AI 线程加 outbox、API/UI 单任务协程、perf 单 k6 进程、integration 单任务步骤 | 由执行底座和任务协议决定，不能强行统一 |
| 心跳间隔策略 | AI 取配置值与租约一半的较小者，API/UI 配置值，integration/perf 取租约三分之一上限 | 不同执行时长和取消粒度需要不同余量 |
| 状态词汇 | 四套协议各自定义 | 控制面已有不同状态机；统一词汇会破坏既有契约 |
| 关闭映射 | API/UI 使用 `canceled`，perf 区分 `canceled`/`stopped`，AI 无停止，integration 使用 unknown | 由控制面支持的状态和外部副作用是否已发生决定 |
| 恢复介质 | outbox、S3 产物、health/evidence 日志、`result.json` | 各项目已有经审计的恢复路径，共享介质会增加跨应用依赖 |
| 快照结构 | 任务/尝试、case/suite、RunSpec、job/step | 业务输入不同；只统一身份和租约字段 |

## 工单 34/38/41/42 的最终语义

- 工单 34：AI 心跳连续失败、被控制面明确拒绝或租约到期后停止执行，迟到结果不提交；结果回传失败写入本地 outbox，只在原租约内重试，不重新调用模型；AI 队列没有停止信号，Worker 不发布 `canceled`。
- 工单 38：API/UI 领取后建立单调时钟租约窗口；心跳被拒或窗口到期时取消在途操作，不产生新副作用；SIGTERM 回传 `canceled`，不把关闭报成 `error`；普通断连不合成结果。
- 工单 41：perf 先把结果写入 `result.json`，再在租约内退避重试完成上报；`LeaseLostError` 立即停止；相同载荷重复上报保持幂等，不产生第二次 k6 运行。
- 工单 42：perf 停止原因按 USER、SHUTDOWN、LEASE_LOST 分别映射为 `canceled`、`stopped`、`stopped`；once 取消终止整个 k6 进程组；数据下载只对 429/5xx 重试。

## 验证入口

根目录一致性测试检查本文覆盖的主题、四个项目、健康探针常量、单调时钟、状态词汇和公共字段：

```bash
python3 -m unittest tests.test_worker_conventions -v
```

各项目按[验证命令矩阵](../commands.md)执行全量测试、Ruff、格式和 mypy。真实控制面断连、SIGTERM、MCP 写入、浏览器和 k6 进程组行为仍需在目标环境验收，模拟测试不能替代。
