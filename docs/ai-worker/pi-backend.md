# Pi 后端

[UI 用例三阶段执行协议](../control-plane/ui-three-stage-generation.md)

Pi 是 `apps/ai-worker` 内的一个执行底座，不是独立项目。业务层通过 `agent/` 门面调用固定版本 Pi 1.3.0 的 RPC；任务类型、技能下载、阶段检查点、产物验证和控制面协议与 Nanobot 后端完全一致。

## 部署选择

编辑唯一配置源 `config/platform.toml`：

```toml
[ai_worker.agent]
backend = "pi" # nanobot（默认）或 pi

[ai_worker.agent.pi]
api = "openai-completions"
context_window_tokens = 500000
max_output_tokens = 65536
stream_idle_timeout_seconds = 300
run_timeout_seconds = 1800
```

模型上下文和输出上限应符合部署所用模型；支持 `openai-completions`、`openai-responses`、`anthropic-messages` 接口。推理模型可配置 `reasoning = true` 和 `thinking_level`。模型 ID、地址和 key 从平台任务凭据获取，不写入镜像或模板。

```sh
python3 scripts/manage.py configure --mode docker
python3 scripts/manage.py compose config --quiet
python3 scripts/manage.py compose up -d --build ai-worker
```

Compose 服务名始终是 `ai-worker`，镜像始终是 `mtx/ai-worker:local`。后端只决定生成的 `worker.toml` 和运行时卷：Pi 使用独立的 `ai-pi-runtime` 和 `ai-pi-logs`，Nanobot 使用 `ai-runtime` 和 `ai-logs`。切换前完成在途任务和人工检查点流程；会话历史不跨底座迁移。

本地 `python3 scripts/manage.py run ai-worker` 同样遵循部署选择，并在 Pi 后端下自动把 `apps/ai-worker/node_modules/.bin` 加入 PATH。首次使用前在该目录执行 `npm ci`。

## 运行时

Python 每次模型调用启动 Pi RPC 子进程，在当前任务工作目录加载下载后的技能。同一任务工作目录内的多阶段或修正通过会话键继续 Pi 历史；不同任务目录隔离会话。每个调用创建独立 agent 目录，模型 key 通过环境变量解析，目录在结束时删除；模型输出仍走业务校验，绝不直接当作平台成功结果。

运行到 `agent_settled` 后返回最终 assistant 文本、stop reason 和调用用量；模型长度截断直接报错，不能发布为完成结果。空闲超时、总时限、取消或异常退出均回收进程组；主 Worker 收到 SIGTERM 时立即终止子进程，保持原 Worker 的立即停止语义。退出后的正常重领由既有控制面机制负责。

实现边界：`agent/pi.py` 管理 RPC、会话、图片输入、受控扩展、超时和进程回收；任务模块只消费归一化后的 `AgentResult`，不解析 RPC 事件。

### 功能测试任务的自主委派

测试点可分组初稿已改为[程序分组并发生成](traceable-test-points.md#初稿按测试对象并发生成)，组内直接执行，不加载自主委派扩展。Pi 后端在未分组的测试点初稿和独立审查中仍显式加载内置 `subagent` 扩展。各 Agent 根据 Skill 的 `references/subagent.md` 自行判断是否委派、决定拆分方式并汇总；测试点修订及其他任务不启用该扩展。完整用例已改为[程序按模块分派并发生成](module-case-generation.md)：每个模块使用独立 Agent、会话和工作目录，最多同时生成 2 个，不再加载自主委派扩展。该调度同样适用于阶段恢复、继续优化和 Nanobot 后端。测试点仍须经过原有格式、引用及独立审查，完整用例沿用原有格式校验和编号规则，人工审核流程不变。

每次模型调用最多委派 8 个子任务，同一调用最多并发 2 个；子任务最长 180 秒（也不超过父调用总超时）。子任务复用任务的模型配置和冻结输入，使用独立 Pi 进程及无持久会话，只开放 `read/grep/find/ls`，不加载扩展，不能再次委派。它们共享任务工作区且工具白名单不构成文件系统沙箱。图片只传给主 Agent，子 Agent 不直接接收图片。任一子任务失败会使该次生成失败，不发布部分结果；子任务明确返回 `CLARIFICATION_REQUIRED:` 时，完整用例阶段按现有澄清流程失败。取消或超时由父进程组统一回收。日志记录子任务数量和可用 token 用量，不记录提示词或产物。并发限制按每次模型调用计算，不是跨 Worker 的全局配额。部署代码前须先发布同一版本的两个 Skill，包含各自的 `references/subagent.md`。

本地切换期间保留旧的 `agent/subagent.mjs` 给已运行的旧 Worker；新代码加载 `agent/subagent_skill.mjs`。确认所有 Worker 均已切换、没有旧进程后再移除旧扩展。

[Pi RPC 官方协议](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md)

## 容器验证

镜像构建后可运行不使用真实模型凭据的 Pi CLI 验收，覆盖工具执行与会话续接：

```sh
docker run --rm --init -e PI_RUNTIME_SMOKE=1 \
  --mount type=bind,source="$PWD/apps/ai-worker/tests",target=/checks,readonly \
  mtx/ai-worker:local python -m unittest discover -s /checks/integration -p test_pi_cli.py -v
```

该验收使用真实 Pi CLI 和本地模拟模型，不代表真实模型生成质量或平台端到端任务已验收。
