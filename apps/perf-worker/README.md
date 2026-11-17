# perf-worker

性能测试执行 Worker。开发与审查先阅读 [AGENTS.md](AGENTS.md)、[项目说明](../../docs/perf-worker/README.md) 和 [开发规则](../../docs/perf-worker/development-rules.md)。

支持控制面 `poll` 模式和本地 `once` 模式：领取性能运行或读取本地运行规格，生成固定 k6 模板所需的执行计划，启动 k6 并把指标写入 Prometheus，再回传或输出结果。

## 启动

```sh
cd apps/perf-worker
uv sync --locked --extra dev
cp config/local.example.toml config/local.toml
# poll 模式：配置 [control_plane].base_url 和 worker_token
uv run --locked mtx-perf-worker --config config/local.toml
```

本地 `once` 排查时，将 `mode` 改为 `"once"` 并设置 `[once].snapshot_file`。

配置由仓库根目录的 `config/platform.example.toml` 和本地忽略的 `config/platform.toml` 统一生成；本地生成文件为 `config/local.toml`。
