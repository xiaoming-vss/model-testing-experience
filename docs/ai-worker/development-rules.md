# AI Worker 开发规则

- 状态：现行
- 负责人：ai-worker maintainer
- 最近复核：2026-11-26
- 复核周期：每季度
- 适用范围：`apps/ai-worker/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

开发和审查 `apps/ai-worker/` 前，必须阅读[通用后端规则](../agents/backend-development.md)、[领域上下文](CONTEXT.md)及相关 ADR。本文件补充模型执行与产物回传的要求，源码和命令默认相对该应用目录。

## 模块与运行边界

- 沿用本项目 Python 3.13、独立 `pyproject.toml`、`uv.lock` 及启动入口；不引入控制面 ORM、Web 服务或直接数据库访问。
- `app/` 装配执行依赖，`worker/` 管理轮询、领取、心跳和运行，`tasks/` 管理各类任务，`platform/` 封装控制面协议，`agent/` 负责执行底座门面与适配器。
- 业务模块不得直接导入 Nanobot SDK 或 Pi RPC；新增底座只扩展 `agent/` 适配器，并实现 `agent/base.py` 的契约。底座专属逻辑（凭据文件、会话、进程回收、超时）留在适配器内。
- 新任务类型必须同时更新分派、任务载荷、执行器、结果解析与控制面消费方；不能只在提示词中添加名称就视为支持新任务。
- 调整并发、停止或中断策略时，必须保留独立任务 workspace 和任务关联身份，并验证心跳及结果回传，不套用其他 Worker 的排空期限。关闭语义固定为：SIGINT 停止领取新任务并等待在途任务完成后退出；SIGTERM 立即终止模型子进程并退出进程，不回传结果，在途尝试由控制面按租约回收。

Pi 和 git 子进程不得继承完整 `os.environ`。Pi 使用 `agent/pi.py` 的 `PI_ENV_ALLOWLIST`（PATH、HOME、临时目录、locale、Windows 启动变量）加父进程 `PI_*`，并由代码显式注入 `MTX_PI_API_KEY`、`PI_CODING_AGENT_DIR`、`PI_OFFLINE` 和 `PI_TELEMETRY`；git 使用 `tasks/git_workspace.py` 的 `GIT_ENV_ALLOWLIST` 加显式 askpass 配置和 `GIT_PASSWORD`。Worker Token、GitLab token、云凭据及其他服务秘密不得进入子进程。新增子进程依赖（如代理或自定义 CA）时必须按最小范围显式加入白名单并补秘密标记回归，不能整体回退到父环境。

## 输入 产物与回传

任务通过控制面领取，权限材料按任务协议获取。技能执行前按当前任务或阶段从控制面取得默认技能，验证下载大小与 SHA-256；失败按既有契约报告，不静默退回旧技能或复用其他运行输入。默认技能和项目自定义技能的参与范围以领域规格为准。

模型输出必须经过对应任务的格式、Schema 和业务校验后回传，不能仅凭可解析 JSON/YAML 或模型自述判定成功。需求分析包含提示性需求评审、材料整理、历史需求关联和历史用例核验四个独立阶段：评审报告只供人工判断，不阻断材料整理，也不传给下游；材料整理审核后的结构化 JSON 直接供相关下游任务使用；历史影响线使用独立的历史需求关联和历史用例核验尝试，核验按冻结规则与用例快照分批。其他任务各自保留契约，不能统一替换成一种输出格式。

功能用例编号复用平台分配和修订认回规则，不信任模型生成的同名值。模型调用恢复、阶段重新执行和结果回传重试必须分别定义；回传失败不能自动重新调用模型。运行日志按通用规则记录任务与阶段标识，不记录完整提示词、输入材料、模型输出或凭据。

异常日志与最终失败回传统一使用 `core/errors.py` 的安全摘要：只保留异常类型、文件/行号/函数名和任务标识。可能携带提示词、输入材料、模型输出或凭据的异常，不得使用 `LOGGER.exception`、`exc_info=True` 或直接拼接 `str(exc)`。Pydantic 校验摘要必须关闭输入值（`include_input=False`），只输出字段路径和校验消息；配置加载失败只输出配置路径、字段路径和修复提示，不输出配置值。回归测试使用秘密标记断言日志和回传均不含该标记。

心跳间隔取配置值与租约一半的较小者，漏掉一次仍来得及续租。本地租约窗口用 `time.monotonic` 从续租请求发出的时刻起算，因此不会晚于控制面自己的窗口。以下任一情况都判定租约失效：窗口到期、心跳连续失败达到阈值、控制面以 `401/403/404/409/410` 拒绝开始、心跳或进度（见 [ADR 0032](../control-plane/adr/0032-replays-are-idempotent-for-the-original-identity.md)）。租约失效后执行器只能在下一个进度检查点停止，且不得再回传结果；迟到的成功响应不能复活已过期的窗口，`started` 或进度响应迟到且已超出窗口时立即判定租约失效：`started` 未完成续租前不启动执行器，进度在当前检查点停止。`started`、心跳和进度请求的超时不超过剩余租约的一半，挂起的请求不能越过本地截止；完成回传使用配置超时，不能因提前放弃而丢掉已完成的结果。心跳失败必须记录安全 warning、状态码和连续失败次数；`400`/`422` 只说明 Worker 发出的请求有问题，不判定租约失效。

AI 队列没有停止信号，Worker 不产生 `canceled`；`TaskStatus.CANCELED` 仅为协议兼容保留。完成回传失败时，最终结果写入本地 outbox 并在租约内重试，不重新调用模型；租约过期条目只保留诊断，不再投递。该路径由 `test_worker_runner.py`、`test_worker_outbox.py`、`test_result_sink.py`、`test_http_client.py` 和 `test_worker_main.py` 覆盖。

## 验证入口

本项目使用 unittest 和 `dev` 依赖组，当前未配置 mypy；公共接口类型按通用规则通过审查和现有契约验证。安装、全量测试、Ruff 和格式检查命令统一见[验证命令矩阵](../commands.md#ai-worker)。

| 变更 | 必须检查的入口 |
| --- | --- |
| 领取、分派、运行及回传 | `tests/unit/test_task_source.py`、`test_worker_dispatcher.py`、`test_worker_runner.py`、`test_worker_outbox.py`、`test_result_sink.py` 及 `test_worker_main.py` |
| 控制面通信与凭据 | `tests/unit/test_http_client.py`，加控制面 `test_worker_contract.py` 和相应任务协议验证 |
| 需求分析 | `tests/unit/tasks/requirement_analysis/test_executor.py`、`test_material_stage.py`、`test_review_stage.py`，加控制面的需求分析专项 |
| 功能用例校验与编号 | `tests/unit/tasks/functional_case_generate/test_validation.py`、`test_case_ids.py`、`test_revision.py` |
| 技能或签名下载 | `tests/unit/platform/test_skills.py`、`test_signed_download.py`，真实存储变化追加显式验收 |
| 其他模型任务 | 对应 `tests/unit/tasks/` 专项，报告和图谱使用各自执行器回归 |

同一单元格中的短文件名相对首个路径所在目录。新增任务必须添加其行为专项；变更模型运行时同时检查 `test_agent_factory.py`、`test_nanobot_adapter.py`、`test_pi_rpc.py` 等实际受影响入口。模拟模型回归不代表真实模型、GitLab 或 S3 已完成验收。
