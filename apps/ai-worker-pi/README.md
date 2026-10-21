# MTX AI Worker Pi

Python 实现，使用 Pi RPC 执行 AI 任务。

- [配置、部署、运行时与验证](../../docs/ai-worker-pi/README.md)
- [开发规则](../../docs/ai-worker-pi/development-rules.md)
- [平台部署](../../docs/deployment.md)

```sh
npm ci
uv sync --locked --group dev
# 从仓库根目录生成配置后，在本目录运行：
PATH="$PWD/node_modules/.bin:$PATH" uv run --locked mtx-ai-worker-pi
```
