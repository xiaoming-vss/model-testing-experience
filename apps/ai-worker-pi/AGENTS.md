# ai-worker-pi 开发指引

遵循根目录 [AGENTS.md](../../AGENTS.md)。业务代码、协议和运行时变更前，阅读[通用后端规则](../../docs/agents/backend-development.md)、[本项目开发规则](../../docs/ai-worker-pi/development-rules.md)和[上下文](../../docs/ai-worker-pi/CONTEXT.md)。

本项目是 Python Worker，Pi CLI 是独立子进程。平台任务与产物契约沿用 AI Worker；专用运行时、依赖、配置及会话均由本项目维护。实现不跨项目 import 原 ai-worker。
