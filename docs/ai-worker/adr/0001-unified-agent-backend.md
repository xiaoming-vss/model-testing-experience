# ADR 0001：收敛为单项目多执行底座

- 状态：已采纳
- 日期：2026-10-31

## 背景

验证阶段同时维护了 `apps/ai-worker`（Nanobot SDK）和 `apps/ai-worker-pi`（Pi RPC）两个独立项目。两份业务代码约 9800 行，除包名、适配器和少量测试外逐字相同，并且已经在同步打补丁。部署侧本来就只启动一个 `ai-worker` 服务，由 `[ai_worker.agent] backend` 二选一。

验证结论确认两个底座都能完成既定任务，因此继续保留两份实现只会放大维护成本，不再带来验证价值。

## 决策

1. `apps/ai-worker` 成为唯一实现，删除 `apps/ai-worker-pi`。
2. 业务层只依赖 `agent/` 门面：`Agent` 协议、`AgentResult`、`task_config_path`、运行时路径与启动校验。
3. Nanobot 和 Pi 各自作为适配器放在 `agent/nanobot.py` 与 `agent/pi.py`；业务任务不出现任何底座名称。
4. 选择方式保持部署侧既有语义：`config/platform.toml` 的 `[ai_worker.agent] backend` 决定生成哪一份 `worker.toml`。
5. 以 Pi 侧实现作为业务基线（审计后业务代码无实质差异；Pi 侧多出的 UI 复核、媒体输入等全部保留）。
6. 一个镜像同时包含两个底座，运行时由 `agent.backend` 选择；Pi 固定版本仍是 1.3.0，启动时校验。
7. 运行时卷保持隔离：`ai-runtime` / `ai-logs` 与 `ai-pi-runtime` / `ai-pi-logs` 不合并，已有运行数据不受影响。
8. `upgrade-config` 把旧的 `[ai_worker_pi.*]` 和 `[ai_worker.nanobot]` 迁移到 `[ai_worker.agent.*]`，已有统一配置优先。

## 后果

- 业务代码只有一份；新增任务、校验规则和提示词不再需要双份同步。
- 新增底座（如 Codex、Grok）只需实现 `agent/base.py` 的契约，不再复制项目。
- 镜像体积增加 Node 运行时和 Pi CLI；Nanobot 部署也会携带，但不需要额外启动进程。
- 配置文件路径统一为 `.runtime/docker/ai-worker.toml`，镜像名统一为 `mtx/ai-worker:local`；旧部署升级后需要重新执行 `configure`。
- 会话历史仍按底座隔离；切换后端不会迁移历史。
