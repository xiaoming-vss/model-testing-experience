# AI Worker Pi

这是独立的 Python 项目 `apps/ai-worker-pi`，通过固定版本 Pi 1.3.0 的 RPC 执行任务。原 `apps/ai-worker` 保留。七类任务、技能下载、阶段检查点、产物验证和控制面协议沿用原项目。

## 部署选择

编辑唯一配置源 `config/platform.toml`：

```toml
[ai_worker.agent]
backend = "pi" # nanobot（默认）或 pi

[ai_worker_pi.worker]
worker_id = "pi-worker-01"
max_concurrent_tasks = 2

[ai_worker_pi.pi]
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

Compose 服务名始终是 `ai-worker`。配置决定其构建目录、镜像、配置文件及数据卷；Pi 使用独立的 `ai-pi-runtime` 和 `ai-pi-logs` 卷。一次部署只生成一个 AI worker 服务，不会默认同时启动两个底座。切换前完成在途任务和人工检查点流程；会话历史不跨底座迁移。切回 `nanobot` 后重建同一服务即可使用原实现。

本地 `python3 scripts/manage.py run ai-worker` 同样遵循部署选择；`run ai-worker-pi` 可显式启动 Pi 项目。需先在对应目录安装 Python 依赖与 `npm ci`，管理脚本会自动把该项目的 `node_modules/.bin` 加入 PATH。

## 运行时

Python 每次模型调用启动 Pi RPC 子进程，在当前任务工作目录加载下载后的技能。同一任务工作目录内的多阶段或修正通过会话键继续 Pi 历史；不同任务目录隔离会话。每个调用创建独立 agent 目录，模型 key 通过环境变量解析，目录在结束时删除；模型输出仍走业务校验，绝不直接当作平台成功结果。

运行到 `agent_settled` 后返回最终 assistant 文本、stop reason 和调用用量；模型长度截断直接报错，不能发布为完成结果。空闲超时、总时限、取消或异常退出均回收进程组；主 Worker 收到 SIGTERM 时立即终止子进程，保持原 Worker 的立即停止语义。退出后的正常重领由既有控制面机制负责。

[开发规则](development-rules.md) · [领域上下文](CONTEXT.md) · [Pi RPC 官方协议](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md)

## 容器验证

镜像构建后可运行不使用真实模型凭据的 Pi CLI 验收，覆盖工具执行与会话续接：

```sh
docker run --rm --init -e PI_RUNTIME_SMOKE=1 \
  --mount type=bind,source="$PWD/apps/ai-worker-pi/tests",target=/checks,readonly \
  mtx/ai-worker-pi:local python -m unittest discover -s /checks/integration -p test_pi_cli.py -v
```

该验收使用真实 Pi CLI 和本地模拟模型，不代表真实模型生成质量或平台端到端任务已验收。
