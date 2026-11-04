# AI Worker（ai-worker）

[UI 用例三阶段执行协议](../control-plane/ui-three-stage-generation.md)

开发与审查先阅读[通用后端规则](../agents/backend-development.md)和[AI Worker 开发规则](development-rules.md)，保留本项目的运行模型、产物契约和验证入口。

接收平台派发的 AI 测试任务，调用 LLM 生成测试产物并回传。领取需求分析、功能/API/UI 用例生成、代码风险分析、测试报告生成、用例执行顺序图谱七类任务。

领域术语与任务类型见 [CONTEXT](CONTEXT.md)。任务执行遵循两条设计约定：技能包由部署侧预置，worker 不下载技能；轮询无锁并行，收到 SIGTERM 立即退出。

## 运行时与依赖

- Python 3.13（`.python-version`），包管理使用 uv（`uv.lock`），构建后端 hatchling
- Python 依赖：`nanobot-ai==0.3.5`（LLM Agent SDK）、`httpx`、`pydantic`、`pyyaml`、`jsonschema`
- Node 运行时：`@earendil-works/pi-coding-agent==1.3.0`，由 `package.json` / `package-lock.json` 固定
- 一个镜像同时包含两个底座，由 `agent.backend` 在启动时选择；不监听任何端口，Compose 中无 `ports`

## 执行底座

业务代码只依赖 `agent/` 门面，Nanobot 与 Pi 是同一契约下的两个适配器：

| backend | 实现 | 运行方式 |
| --- | --- | --- |
| `nanobot`（默认） | `agent/nanobot.py` | Python 进程内调用 `nanobot-ai` SDK |
| `pi` | `agent/pi.py` | 每次模型调用启动固定版本 Pi CLI 的 RPC 子进程 |

选择方式、Pi 的会话/超时/进程回收语义和容器验收见 [Pi 后端](pi-backend.md)；收敛决策见 [ADR 0001](adr/0001-unified-agent-backend.md)。两个底座的任务类型、技能下载、阶段检查点、产物校验和控制面协议完全一致；切换前处理在途任务和人工检查点，会话历史不跨底座迁移。

## 源码结构

`apps/ai-worker/src/testing_agent_ai_worker/`：

| 路径 | 作用 |
| --- | --- |
| `main.py`、`__main__.py` | 入口：加载配置、校验后端运行时、初始化日志、进入 `run_worker` |
| `agent/` | 后端门面与适配器：`base.py`（契约）、`nanobot.py`、`pi.py`、`prompt.py`、`paths.py`、`config_builder.py` |
| `app/bootstrap.py` | 构建 poller 与 runner，提供 `run_worker` 与 `run_poll_once` |
| `worker/` | `loop.py`、`poller.py`、`runner.py`、`dispatcher.py`、`executor.py`、`lifecycle.py` |
| `tasks/` | 七类任务各自的实现，另有 `result_summary.py` |
| `platform/` | 与控制面通信：`http_client.py`、`task_source.py`、`result_sink.py`、`schemas.py`、`errors.py` |
| `config/`、`logging/` | 配置加载与日志设置 |

## 配置

读取 `config/worker.toml`（容器内 `/app/config/worker.toml`）。**没有**类似 `APP_CONF` 的路径覆盖机制，只能通过环境变量覆盖以下字段：

| 环境变量 | 覆盖的配置项 |
| --- | --- |
| `TESTING_AGENT_PLATFORM_BASE_URL` | `platform.base_url` |
| `TESTING_AGENT_WORKER_TOKEN` | `platform.worker_token` |
| `TESTING_AGENT_NANOBOT_RUNTIME_ROOT` | `agent.nanobot.runtime_root` |
| `TESTING_AGENT_PI_RUNTIME_ROOT` | `agent.pi.runtime_root` |

其余配置只能改文件，顶层段为 `[worker]`、`[platform]`、`[agent]`、`[logging]`。`[agent]` 结构如下；部署生成时只写入选中的后端子段：

```toml
[agent]
backend = "nanobot"

[agent.nanobot]
runtime_root = "/data/runtime"
stream_idle_timeout_seconds = 300
provider_request_timeout_seconds = 300

[agent.pi]
runtime_root = "/data/runtime"
executable = "pi"
run_timeout_seconds = 1800
api = "openai-completions"
context_window_tokens = 500000
max_output_tokens = 65536
```

Nanobot 后端启动时还会写入 `NANOBOT_STREAM_IDLE_TIMEOUT_S` 与 `NANOBOT_OPENAI_COMPAT_TIMEOUT_S`。

## 命令

在 `apps/ai-worker/` 下执行：

```sh
uv sync --locked                                  # 安装 Python 依赖
npm ci                                            # Pi 后端需要固定版本 CLI
uv run mtx-ai-worker                              # 启动（后端由配置决定）
uv run python -m unittest discover -s tests       # 测试（358 项，3 项按环境跳过）
uv run ruff check .                               # Lint
```

测试使用 `unittest` 编写，因此运行方式不是 pytest；开发依赖组只声明了 ruff。

## 与控制面的交互

反向轮询 `platform.base_url`，请求头固定 `X-Worker-Token`（旧名 `X-Worker-Key` 已不使用），路径由配置给出，默认为：

`/internal/ai-worker/tasks/claim`、`/snapshot`、`/started`、`/heartbeat`、`/progress`、`/completed`、`/llm-credentials`

领取、快照、进度和完成回传使用 `attemptId` 表示本次派发的阶段尝试；面向客户端的独立任务执行 ID 只在控制面接口以 `runId` 出现。两者不可互换，Worker 不应把执行 ID 当作队列尝试标识。

进度回传只发送当前阶段、阶段状态、配置中间产物和结果摘要；不再发送 `remediation` 或不被持久化的结果正文。完成回传发送状态、结果 YAML、中间产物、结果摘要和错误信息，失败原因通过 `errorMessage` 展示。旧版 Worker 多发的字段由平台按既有反序列化策略忽略。

## 默认技能按需获取

Worker 每次执行前按任务类型／阶段从控制面获取默认技能清单，直读 S3 并验证文件大小和 SHA-256。技能恢复到任务独立 workspace 中，不再手工向项目目录放置技能；本期每次重新获取当前内容，不做历史版本或跨运行缓存。项目自定义技能不自动加入任务。

平台初始化与更新方式见 [Skill 库维护](../control-plane/skills.md)。缺少默认技能或下载失败时任务报错，不回退旧目录。目前初始源中不含 `code-risk-analysis`，对应任务需补齐后使用。

- [S3 任务文件读取](file-storage.md)
- [需求分析两阶段与 JSON 产物设计](requirement-analysis-two-stage-design.md)（实施前设计）

## API / UI 用例输出自动修正（2026-10-09）

API 的 OpenAPI 配置提取、API 用例 YAML 生成，以及 UI 用例 YAML 生成均支持输出校验失败后的自动修正。每个阶段最多追加 2 次模型调用（含首次最多 3 次），只有验证通过才发布本阶段结果。API 提取结果先校验再传给生成阶段；生成阶段的修正不重复执行已成功的提取。UI 修正复用本次已下载的源码根目录，不重复下载源码归档。

API 提取校验非空接口映射、snake_case 名称、path/method 与已定义的参数分区；API 用例校验 `cases` 结构、字段类型、排序、名称唯一、方法、请求体、提取及断言规则，按平台导入契约和技能输出约定执行。生成端不查询目标集合已有名称，导入时的数据库冲突仍由控制面处理。UI 沿用既有步骤、关键字、定位器、操作值、比较符和顺序校验。YAML 重复键、非法结构、非 JSON 兼容值不作为有效产物接受。

修正输入包含原始输入和用户要求、上一版输出及校验错误，保持相同任务会话；不通过编造接口、字段、定位器或预期来修复输出。网络、模型服务、鉴权、源码准备、回传错误不触发此循环；模型明确报告长度截断时直接失败。业务执行和真实页面行为仍需后续验收，格式校验不能证明用例业务正确。

修正期间复用 `outputValidation` 摘要上报 `repairAttempt/maxRepairs/status`。API 生成阶段进度保留已验证的提取 JSON；UI 进度保留源码位置，修正失败不发布非法用例。每轮输出和校验错误保存在任务 workspace 的 `diagnostics/api-output` 或 `diagnostics/ui-output`，文件权限 0600，不保存模型连接设置或完整提示词。

验证：Worker 全量 232 项测试、控制面 API/UI 导入与 Worker 契约 40 项回归通过；API 标准技能样例（含提取和断言规则）、UI 全部支持关键字样例同时通过 Worker 验证器与控制面导入验证。Worker Ruff 与修改范围格式检查通过。未调用真实模型生成或执行 API/UI 用例。

## UI YAML 人工补全

UI 候选生成接受步骤级 `missingFields` 结构化待补项，明确字段、操作、目标、值和原因；对应字段可为 null，其余已知字段仍按关键字规则校验。该候选原文回传而不强制模型修复。用户补齐同一 YAML 后再导入；正式导入/执行门禁见[UI YAML 待补内容](../control-plane/ui-yaml-completion.md)。全部目标排除时允许空列表表示零候选，不能将生成成功当成可执行或测试通过。

### UI YAML 缺口复核

第三阶段先按模块完成原格式、字段和名称顺序硬校验；只有这些确定性错误进入同模块最多两轮自愈。完整合并通过后将草稿保存为诊断目录的 `candidate.yaml`，再逐模块通过独立模型会话提供辅助复核。复核检查 `missingFields` 的可补全性、字段用途和设计目标覆盖，读取原始用例、已审核设计、控件清单、源码与候选 YAML。复核意见不触发 YAML 重生成，也不使生成失败。报告附在 `resultSummaryJson.uiSemanticReview`，不加入用户 YAML，最终仍需人工审核。

每模块复核总时限为 120 秒，报告格式最多修复一次；调用失败、超时、截断或格式仍不合法时标记 `incomplete`，保留草稿并继续交付。取消及权限异常继续传播。报告记录完整 YAML 的 SHA-256 和合并后的用例/步骤位置；控制面发现草稿被修改后展示 `stale`，不将旧报告当作新草稿的结论。报告状态 `completed` 仅指复核完成，不代表没有问题或用例可直接导入。

`assert_visible` / `assert_hidden` / `sleep` 的 `operationValue` 表示等待毫秒数，不可标成缺少业务期望。运行时生成值不能作为执行前待补数据；无法忠实实现的已审核目标必须报告冲突，不以删断言、改预期或人工核对绕过。诊断目录保留每次生成原文和复核报告，验证不修改产物。该检查只收紧新生成流程，历史导入兼容契约不变。

每次第三阶段生成/修复及内部复核均使用新会话。调用输入包含完整的当前模块材料、候选或错误反馈，避免重复会话历史叠加大型 YAML 导致上下文溢出；不依赖历史聊天恢复任务。

需求生成链的新 API 两阶段运行使用快照标记 `apiWorkflowVersion: api_two_stage/1.0`。`openapi_extract` 只调用 `openapi-test-config-extractor` 并在结果校验通过后等待审核；`generate` 读取已选审核版本调用 `api-cases-yaml-generator`。每次只获取当前阶段的 Skill；旧运行保持原先自动串联两个 Skill 的协议。
