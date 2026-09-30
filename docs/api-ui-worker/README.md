# API/UI Worker（api-ui-worker）

在单进程内执行 API 与 UI 两类自动化任务：领取控制面派发的任务，用 Playwright 或 HTTP 执行用例，将截图与 Trace ZIP 通过短期签名直传私有 S3，向平台回传稳定文件引用。

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
| `control_plane/client.py`、`control_plane/artifacts.py` | 控制面客户端及 S3 产物上传 |
| `poller/task_poller.py` | 任务轮询 |
| `contracts/types.py` | 任务与结果类型 |
| `core/` | `config.py`、`logger.py` |

`src/` 下残留 `mtx_api_ui_worker.egg-info/` 与 `testing_agent_api_ui_worker.egg-info/` 两个历史打包目录。

## 配置

读取应用根目录的 `config.toml`（容器内挂载为 `/app/config.toml`）。**没有环境变量覆盖机制**，并有测试固化该行为。

```toml
mode = "poll"                 # poll 或 once

[control_plane]               # base_url、worker_token
[worker]                      # id、poll_interval_ms、request_timeout_ms、heartbeat_interval_ms
[ui]                          # artifacts_dir（临时目录）、headless、slow_mo_ms、
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

Worker 不再监听文件下载端口，9010 截图服务已移除。截图和 Trace 在任务临时目录生成，通过 Worker 令牌向控制面申请签名 POST，再用独立 HTTP 客户端直传 S3；长期 S3 密钥不配置给 Worker。文件核验完成后回传 `/v1/files/{fileId}/download`，前端经过项目权限校验取得短期下载票据。

上传使用线程执行，保持主循环心跳。上传失败导致结果回传失败并保留临时文件供排障，不回退本地 URL；只有平台接受最终结果后才清理本次已上传的临时文件。`once` 离线调试模式没有平台任务归属，产物只作为临时调试数据。


## 与平台的交互

反向轮询控制面，请求头固定 `X-Worker-Token`：

- UI 任务：`/internal/ui-worker/tasks/claim` 与 `/{task_id}/snapshot`，文件授权与完成为 `/{task_id}/files/uploads`、`/{task_id}/files/{file_id}/complete`；控制面校验 Worker、租约、执行人和项目归属
- API 任务：`/internal/api-worker/tasks/claim` 与 `/{task_id}/snapshot`、`/started`、`/heartbeat`、`/completed`，集合任务另有 `/collection-items/{item_id}/started` 与 `/completed`

该服务没有健康检查端点，Dockerfile 中也没有 `HEALTHCHECK`，Compose 因此不对它设置健康检查条件。
