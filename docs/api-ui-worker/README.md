# API/UI Worker（api-ui-worker）

在单进程内执行 API 与 UI 两类自动化任务：领取控制面派发的任务，用 Playwright 或 HTTP 执行用例，回传结果并把截图等工件通过只读 HTTP 服务暴露给浏览器。

## 运行时与依赖

- Python 3.12（`.python-version`），包管理使用 uv（`uv.lock`，另有 `requirements.txt`）
- 依赖：`playwright`、`httpx`
- 镜像基于 `mcr.microsoft.com/playwright/python:v1.60.0-noble`，Dockerfile 会断言 Playwright 版本恰为 1.60.0，升级 Playwright 需同步改镜像标签
- 开发依赖在 `[project.optional-dependencies] dev`，需要 `--extra dev` 才会装入
- Compose 中为该服务设置 `shm_size: 1gb`，浏览器需要足够的共享内存

## 源码结构

`apps/api-ui-worker/src/test_worker/`：

| 路径 | 作用 |
| --- | --- |
| `__main__.py` | 入口与主循环，含 `poll` 与 `once` 两种模式 |
| `ui/` | UI 执行：`case_runner.py`、`suite_runner.py`、`step_executor.py`、`step_normalizer.py`、`locator.py`、`browser_options.py`、`templates.py` |
| `api/` | API 执行：`case_runner.py`、`collection_runner.py`、`http_client.py`、`rule_runtime.py`、`template_runtime.py` |
| `control_plane/client.py` | 控制面客户端 |
| `poller/task_poller.py` | 任务轮询 |
| `contracts/types.py` | 任务与结果类型 |
| `core/` | `config.py`、`artifact_server.py`、`logger.py` |

`src/` 下残留 `mtx_api_ui_worker.egg-info/` 与 `testing_agent_api_ui_worker.egg-info/` 两个历史打包目录。

## 配置

读取应用根目录的 `config.toml`（容器内挂载为 `/app/config.toml`）。**没有环境变量覆盖机制**，并有测试固化该行为。

```toml
mode = "poll"                 # poll 或 once

[control_plane]               # base_url、worker_token
[worker]                      # id、poll_interval_ms、request_timeout_ms、heartbeat_interval_ms
[ui]                          # artifacts_dir、artifacts_bind_host、artifacts_port、
                              # artifacts_base_url、headless、slow_mo_ms、
                              # trace_enabled、screenshot_on_failure
[once]                        # snapshot_file，once 模式读取本地快照调试用
```

未配置 `worker.id` 时自动生成 `api-ui-worker-<hostname>-<pid>`。`once` 模式使用本地快照文件，便于不依赖控制面调试单个任务。

## 命令

在 `apps/api-ui-worker/` 下执行：

```sh
uv sync --locked --extra dev                      # 安装依赖
uv run playwright install chromium                # 安装浏览器（Linux 首次可加 --with-deps）
uv run mtx-api-ui-worker                          # 启动
uv run --extra dev pytest                         # 测试（34 项）
uv run --extra dev ruff check .                   # Lint
```

## 对外接口

默认监听 9010，提供只读工件服务：仅响应 `.png` 文件，禁止目录列表，带 `Access-Control-Allow-Origin: *`。仅在配置了 `artifacts_base_url` 时启动。该地址会被写入截图 URL 供浏览器访问，因此必须是浏览器可达的地址，而不只是容器内地址。

## 与平台的交互

反向轮询控制面，请求头固定 `X-Worker-Token`：

- UI 任务：`/internal/ui-worker/tasks/claim` 与 `/{task_id}/snapshot`
- API 任务：`/internal/api-worker/tasks/claim` 与 `/{task_id}/snapshot`、`/started`、`/heartbeat`、`/completed`，集合任务另有 `/collection-items/{item_id}/started` 与 `/completed`

该服务没有健康检查端点，Dockerfile 中也没有 `HEALTHCHECK`，Compose 因此不对它设置健康检查条件。
