# Pi Worker 开发规则

业务流程与校验遵循 [AI Worker 开发规则](../ai-worker/development-rules.md)，其中 Nanobot 运行时约定由本文件替代。

- 依赖、锁文件、Dockerfile 和 Python 启动入口保持独立。Pi 版本同时固定在 package.json、package-lock.json 和启动版本校验常量中。
- `pi_runtime/client.py` 管理 RPC、会话、图片输入、超时及进程回收；任务模块只使用运行结果，不解析 RPC。
- `prompt` 接受响应不代表完成，必须等待 `agent_settled`；模型错误、取消和长度截断保留独立语义，不能把中间工具消息当成最终产物。
- 凭据使用私有临时配置和子进程环境，退出时清理临时目录。错误日志只保留安全分类，不记录提示词、完整响应或凭据。
- 新项目无需兼容 Nanobot 配置或会话。默认只启动部署选定的一个底座，变更协议时同时验证原 ai-worker 的消费方式。

在 apps/ai-worker-pi 执行：

```sh
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check src tests
```

RPC 专项必须覆盖确认与完成事件顺序、恢复后的最终消息、错误、截断、异常退出、超时、取消、会话和图片。平台业务专项保留复制后的测试。编排变更还运行根目录测试和 Compose 配置检查。
