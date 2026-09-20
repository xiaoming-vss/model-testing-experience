# AI Worker（ai-worker）

接收平台派发的 AI 测试任务，调用 LLM 生成测试产物并回传。领取需求分析、功能/API/UI 用例生成、代码风险分析、测试报告生成六类任务。

领域术语与任务类型见 [CONTEXT](CONTEXT.md)。任务执行遵循两条设计约定：技能包由部署侧预置，worker 不下载技能；轮询无锁并行，收到 SIGTERM 立即退出。

## 运行时与依赖

- Python 3.13（`.python-version`），包管理使用 uv（`uv.lock`），构建后端 hatchling
- 依赖极简：`nanobot-ai==0.3.5`（LLM Agent SDK）、`httpx`、`pydantic`、`pyyaml`
- 不监听任何端口，Compose 中无 `ports`

## 源码结构

`apps/ai-worker/src/testing_agent_ai_worker/`：

| 路径 | 作用 |
| --- | --- |
| `main.py`、`__main__.py` | 入口：加载配置、初始化日志、进入 `run_worker` |
| `app/bootstrap.py` | 构建 poller 与 runner，提供 `run_worker` 与 `run_poll_once` |
| `worker/` | `loop.py`、`poller.py`、`runner.py`、`dispatcher.py`、`executor.py`、`lifecycle.py` |
| `tasks/` | 六类任务各自的实现，另有 `result_summary.py` |
| `platform/` | 与控制面通信：`http_client.py`、`task_source.py`、`result_sink.py`、`schemas.py`、`errors.py` |
| `config/`、`logging/` | 配置加载与日志设置 |
| `nanobot/`、`nanobot_runtime/` | 运行时装配与提示词 |

`nanobot/` 与 `nanobot_runtime/` 两个目录职责有重叠（都含 `config_builder.py` 与 `paths.py`），是待收敛的历史结构。

## 配置

读取 `config/worker.toml`（容器内 `/app/config/worker.toml`）。**没有**类似 `APP_CONF` 的路径覆盖机制，只能通过环境变量覆盖三个字段：

| 环境变量 | 覆盖的配置项 |
| --- | --- |
| `TESTING_AGENT_PLATFORM_BASE_URL` | `platform.base_url` |
| `TESTING_AGENT_WORKER_TOKEN` | `platform.worker_token` |
| `TESTING_AGENT_NANOBOT_RUNTIME_ROOT` | `nanobot.runtime_root` |

其余配置只能改文件，顶层段为 `[worker]`（`worker_id`、`poll_interval_seconds`、`heartbeat_interval_seconds`、`max_concurrent_tasks`、`run_once`）、`[platform]`（`base_url`、`worker_token` 及各任务回调路径）、`[nanobot]`（`runtime_root`、超时）、`[logging]`。启动时还会写入 `NANOBOT_STREAM_IDLE_TIMEOUT_S` 与 `NANOBOT_OPENAI_COMPAT_TIMEOUT_S`。

## 命令

在 `apps/ai-worker/` 下执行：

```sh
uv sync --locked                                  # 安装依赖
uv run mtx-ai-worker                              # 启动
uv run python -m unittest discover -s tests       # 测试（196 项）
uv run ruff check .                               # Lint
```

测试使用 `unittest` 编写，因此运行方式不是 pytest；开发依赖组只声明了 ruff。

## 与控制面的交互

反向轮询 `platform.base_url`，请求头固定 `X-Worker-Token`（旧名 `X-Worker-Key` 已不使用），路径由配置给出，默认为：

`/internal/ai-worker/tasks/claim`、`/snapshot`、`/started`、`/heartbeat`、`/progress`、`/completed`、`/llm-credentials`

## 技能预置

按项目在 `nanobot.runtime_root` 下预置技能目录，容器内为 `/data/runtime/workspaces/project-<项目ID>/skills/`，每个技能目录包含 `SKILL.md`。本地运行时对应 `apps/ai-worker/runtime/workspaces/`。缺少技能时相关任务无法执行，部署见 [部署指南](../deployment.md)。
