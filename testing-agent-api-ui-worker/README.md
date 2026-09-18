# testing-agent-api-ui-worker

`testing-agent-api-ui-worker` 是 `testing-agent` 的独立 API/UI 测试执行器项目。它在一个 worker 进程内支持：

- UI Playwright 用例和测试集任务
- API HTTP 单用例和集合任务
- poll 模式轮询 Go 控制面领取任务
- once 模式基于本地 snapshot 调试 UI 或 API

## 项目结构

```text
testing-agent-api-ui-worker/
├── config.toml
├── config.example.toml
├── pyproject.toml
├── README.md
├── src/
│   └── test_worker/
│       ├── __main__.py
│       ├── api/             # API HTTP runner、规则和模板运行时
│       ├── contracts/       # worker 内部数据类型
│       ├── control_plane/   # Go 控制面客户端
│       ├── core/            # 配置和日志
│       ├── poller/          # poll 模式任务调度
│       └── ui/              # Playwright UI runner
└── tests/
```

## 安装

```powershell
uv sync
uv run playwright install chromium
```

开发依赖：

```powershell
uv sync --extra dev
```

## 配置

默认读取当前工作目录或项目根目录下的 `config.toml`。Worker 不读取 `.env` 或环境变量，所有本地启动配置都放在 TOML 中。

常用配置：

```toml
mode = "poll"

[control_plane]
base_url = "http://127.0.0.1:8000"
worker_token = "replace-with-worker-token"

[worker]
id = ""
poll_interval_ms = 3000
request_timeout_ms = 15000
heartbeat_interval_ms = 10000

[ui]
artifacts_dir = "./artifacts"
artifacts_bind_host = "127.0.0.1"
artifacts_port = 9010
artifacts_base_url = "http://127.0.0.1:9010"
headless = true
slow_mo_ms = 0
trace_enabled = true
screenshot_on_failure = true

[once]
snapshot_file = ""
```

`worker_token` 要和 Go 后端配置里的 `security.worker.key` 一致。

配置 `artifacts_base_url` 后，poll 模式会启动仅允许读取 PNG 截图的服务，并在上报结果时把
本地 `screenshotPath` 转换为可直接访问的 URL。该临时服务不鉴权且不允许目录浏览。
如果前端不在 worker 本机，请把 `127.0.0.1` 替换成前端可以访问的 worker IP 或域名；
同时按需将 `artifacts_bind_host` 改为 `0.0.0.0` 并通过防火墙限制访问来源。多个 worker
必须分别配置可访问的地址或端口。

## 启动

poll 模式：

```powershell
cd D:\GoProjects\testing-agent-api-ui-worker
uv run python -m test_worker
```

once 模式：把 `config.toml` 改成：

```toml
mode = "once"

[once]
snapshot_file = "./snapshot.json"
```

然后启动：

```powershell
uv run python -m test_worker
```

`snapshot.json` 可以是 `/internal/ui-worker/*/snapshot` 或 `/internal/api-worker/*/snapshot` 返回内容，也可以直接是其中的 `caseRun`、`suiteRun` 或 `collectionRun`。

安装后也可以使用脚本入口：

```powershell
uv run testing-agent-api-ui-worker
```

## Docker 运行

镜像固定使用与 `uv.lock` 一致的 Playwright `1.60.0`，并已包含 Chromium 及其
Linux 系统依赖。构建镜像：

```powershell
docker build -t testing-agent-api-ui-worker:dev .
```

复制一份容器专用配置，不要把实际令牌写进镜像：

```powershell
Copy-Item config.example.toml config.docker.toml
```

至少需要调整以下配置：

```toml
[control_plane]
# 必须是容器内可访问的地址，不能使用指向容器自身的 127.0.0.1。
base_url = "http://host.docker.internal:8011"
worker_token = "replace-with-worker-token"

[ui]
artifacts_dir = "/app/artifacts"
artifacts_bind_host = "0.0.0.0"
artifacts_port = 9010
# 改成浏览器或 testing-agent 前端能够访问的 worker 地址。
artifacts_base_url = "http://127.0.0.1:9010"
headless = true
```

启动 poll worker：

```powershell
docker run --rm --init --ipc=host `
  --name testing-agent-api-ui-worker `
  -p 9010:9010 `
  -v "${PWD}/config.docker.toml:/app/config.toml:ro" `
  -v "${PWD}/artifacts:/app/artifacts" `
  testing-agent-api-ui-worker:dev
```

Worker 会把容器的 SIGTERM/SIGINT 转换为异步取消，以便停止心跳、清理浏览器和截图
服务，并为已领取的任务上报关闭错误。`--init` 用于回收孤儿浏览器子进程，
`--ipc=host` 可避免 Chromium 因共享内存不足而崩溃。Linux 上若控制面运行在宿主机，需要额外添加
`--add-host=host.docker.internal:host-gateway`。容器默认按 Playwright 官方的可信
端到端测试模式以 root 运行；如果任务会访问不可信站点，应使用非 root 用户及
Playwright 官方 seccomp 配置进一步隔离。

## 验证

```powershell
uv run python -m compileall src/test_worker
uv run python -m unittest tests.test_config -v
uv run pytest
```
