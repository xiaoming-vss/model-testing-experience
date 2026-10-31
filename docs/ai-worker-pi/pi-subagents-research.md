# Pi 子 Agent 适配调研

核验日期：2026-10-29。以本仓库 `apps/ai-worker-pi/package.json` 和锁文件固定的 `@earendil-works/pi-coding-agent@1.3.0` 为准，外部链接固定到同版本标签。本记录是可行性分析，未实现运行时变更。

## 官方能力

Pi 核心不默认提供子 Agent；可通过 extension 实现。官方提供 `subagent` 示例扩展：为每次委派启动独立 Pi 进程、隔离上下文，支持单任务、并行和顺序链式委派。示例限制每次最多 8 个并行任务、同时执行 4 个，属于示例策略，不是平台容量保证。[官方说明](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/README.md)、[示例文档](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/examples/extensions/subagent/README.md)

示例通过 `pi --mode json -p --no-session` 启动子进程，支持按 Agent 指定工具和模型。上下文隔离并不等于文件隔离：默认仍使用父任务工作目录；并行产物必须另行分目录。示例没有完整复制父进程 CLI 的技能路径和资源隔离参数，接入时需要显式传递工作区技能、平台模型配置及资源边界。[示例源码](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/examples/extensions/subagent/index.ts)

## 当前 Worker 的差距

本地 `pi_runtime/client.py` 通过 Python 启动 RPC 子进程，显式设置 `--no-extensions`，并向临时 `PI_CODING_AGENT_DIR` 写入模型设置。现状不能只靠提示词调用官方子 Agent 示例，需要增加受控扩展装载，或由 Python 编排多个独立 Pi 会话。代码位置：[运行时客户端](../../apps/ai-worker-pi/src/testing_agent_ai_worker_pi/pi_runtime/client.py)。

RPC 可以承载扩展工具，但扩展 UI 有独立协议：`confirm/select/input/editor` 发出请求后等待客户端应答。尤其 1.3.0 的 RPC 中 `ctx.hasUI` 为真，不能用它判断是否为无交互环境。官方示例在未信任项目中使用项目 Agent 时可能请求确认；后台 Worker 必须预先确定 Agent 来源和策略，或实现应答，避免等待无人处理的对话。[RPC 扩展 UI](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/rpc-extension-ui.md)

官方推荐以 `agent_settled` 判断本轮不再自动继续；`agent_end` 后仍可能重试、压缩或恢复。增加子 Agent 时应同时检查现有客户端的完成事件语义。[RPC 生命周期](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/rpc.md)

取消方面，官方示例监听 AbortSignal 后向直接子进程发送 SIGTERM，并尝试升级 SIGKILL；这不应当被视为完整进程树清理保证。本项目已经 `start_new_session=True` 并最终 `killpg` 清理进程组，应保留并用实际子 Agent 测试验证；扩展额外创建脱离进程组的进程则需要额外管理。这是基于本地和官方源码的工程判断，而非已复现故障。[示例取消实现](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/examples/extensions/subagent/index.ts#L382-L391)

## 建议

优先由 Python Worker 固定拆分任务，使用独立 session 和输出目录并行运行 Pi；初期并发设为 2–3，再根据模型限流和耗时调整。原始需求理解及全局规则先统一，按模块展开需求分析／用例，最后集中校验覆盖、去重及分配编号。阶段之间保留依赖，不将所有阶段同时启动。

只有需要主模型自主决定委派对象和任务粒度时，再引入受控 `subagent` extension。两种方式都需要子任务超时、失败重试、成本汇总、取消传播及确定性的结果合并。并行可以降低独立子任务的墙钟耗时；重复输入和汇总可能增加 token 成本，不能保证质量或总成本自动改善。
