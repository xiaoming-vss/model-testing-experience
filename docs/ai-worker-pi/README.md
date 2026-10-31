# AI Worker Pi

[UI 用例三阶段执行协议](../control-plane/ui-three-stage-generation.md)

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

## UI YAML 人工补全

UI 候选生成接受步骤级 `missingFields` 结构化待补项，明确字段、操作、目标、值和原因；对应字段可为 null，其余已知字段仍按关键字规则校验。该候选原文回传而不强制模型修复。用户补齐同一 YAML 后再导入；正式导入/执行门禁见[UI YAML 待补内容](../control-plane/ui-yaml-completion.md)。全部目标排除时允许空列表表示零候选，不能将生成成功当成可执行或测试通过。

### UI YAML 缺口复核

第三阶段先按模块完成原格式、字段和名称顺序硬校验；只有这些确定性错误进入同模块最多两轮自愈。完整合并通过后将草稿保存为诊断目录的 `candidate.yaml`，再逐模块通过独立模型会话提供辅助复核。复核检查 `missingFields` 的可补全性、字段用途和设计目标覆盖，读取原始用例、已审核设计、控件清单、源码与候选 YAML。复核意见不触发 YAML 重生成，也不使生成失败。报告附在 `resultSummaryJson.uiSemanticReview`，不加入用户 YAML，最终仍需人工审核。

每模块复核总时限为 120 秒，报告格式最多修复一次；调用失败、超时、截断或格式仍不合法时标记 `incomplete`，保留草稿并继续交付。取消及权限异常继续传播。报告记录完整 YAML 的 SHA-256 和合并后的用例/步骤位置；控制面发现草稿被修改后展示 `stale`，不将旧报告当作新草稿的结论。报告状态 `completed` 仅指复核完成，不代表没有问题或用例可直接导入。

`assert_visible` / `assert_hidden` / `sleep` 的 `operationValue` 表示等待毫秒数，不可标成缺少业务期望。运行时生成值不能作为执行前待补数据；无法忠实实现的已审核目标必须报告冲突，不以删断言、改预期或人工核对绕过。诊断目录保留每次生成原文和复核报告，验证不修改产物。该检查只收紧新生成流程，历史导入兼容契约不变。

每次第三阶段生成/修复及内部复核均使用新会话。调用输入包含完整的当前模块材料、候选或错误反馈，避免重复会话历史叠加大型 YAML 导致上下文溢出；不依赖历史聊天恢复任务。
