# MTX AI Worker

项目文档已统一到 [docs/ai-worker](../../docs/ai-worker/README.md)。

- [开发、配置与项目检查](../../docs/ai-worker/README.md)
- [Pi 后端运行时](../../docs/ai-worker/pi-backend.md)
- [整套平台部署与独立启动](../../docs/deployment.md)
- [全部文档](../../docs/README.md)

安装依赖并生成配置后，在本目录独立启动：

```sh
uv sync --locked        # Python 依赖
npm ci                  # 仅 Pi 后端需要固定版本 CLI
uv run mtx-ai-worker    # 执行底座由 worker.toml 的 agent.backend 决定
```
