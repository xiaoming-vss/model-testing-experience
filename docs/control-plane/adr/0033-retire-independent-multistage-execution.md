# ADR 0033：退役独立多阶段执行

- 状态：已接受
- 日期：2026-11-26
- 取代：—
- 被取代：—
- 关联：[ADR 0010](0010-unified-ai-execution.md)、[ADR 0014](0014-pre-release-single-baseline.md)、[需求生成链](../generation-chain.md)、[数据库结构](../database-schema.md)

## 背景

2026-11-17 的提交 `55d5ce3b`（"retire legacy AI task routes"）删除了独立 function/API/UI 任务的路由和 handler，由需求生成链取代。服务层没有同步收敛：`services/standalone_*.py` 14 个文件、两个 standalone 仓库文件和 `GenerationStageWorkflow` 仍保留创建、派发、检查点、继续、修订和重试路径，但没有任何生产入口。`WorkerTaskService` 每次 AI 事件仍先执行一次恒为假的 `is_standalone` 探测；`AiExecution` 同时存在独立执行专用列和生成链使用的执行身份列，形成两套状态事实源。Studio 仍保留 `!candidate` 分支和旧 AI 任务接口调用。

ADR 0010 和 ADR 0014 规定 v1 只支持空库初始化，删除的独立执行不会出现在任何受支持数据库中。

## 决策

1. 删除独立多阶段执行整族：14 个 `services/standalone_*.py`、`repositories/standalone_execution.py`、`repositories/standalone_history.py`、`repositories/standalone_import.py`、`services/ai_stage_workflow.py`、三个旧 AI 任务 router 及其 handler、provider，以及 11 个 standalone 测试文件。
2. `lock_or_create_stage` 只保留一份，位于 `repositories/auxiliary_execution.py`，接收 `stage_name` 并返回 `(stage, created)`；辅助执行使用默认 `generate`，生成链传入自己的阶段名。
3. `GenerationRunLauncher.launch` 只接受代码风险和仓库画像两类辅助任务。function/API/UI 的启动、快照组装、API 三阶段检查点和独立执行派发全部删除。
4. `WorkerTaskService` 的 AI 分支只分派给 `DirectStageWorkerService`；独立执行的领取、快照、开始、心跳、停止状态、完成、进度、凭据和需求文档分支删除。`ensure_worker_match` 仍被 API/UI 路径使用，保留。
5. `AiExecution` 只保留执行身份、所属任务、发起者和创建时间。只由独立执行写入的 7 个列（`workflow_status`、`current_stage`、`checkpoint_enabled`、`trigger_type`、`source_snapshot_json`、`started_at`、`finished_at`）从模型和唯一 baseline 中删除，不新增迁移。
6. AI Worker 只读取当前快照字段：删除 8 个顶层兼容字段、`claim_id` 及别名、15 个重复 metadata 键和两个死 `TaskProgress` 字段；`task_type` 改为必填，`workflow_version` 同时接受声明的别名。
7. Studio 删除 `!candidate` 旧分支、旧 AI 任务接口函数和对应类型、旧运行历史属性、产物框架的 Modal 分支和非侧栏布局；重定向只保留文档登记的两条。

## 后果

- AI 任务的事件处理只剩一次阶段尝试分派，`ai_executions` 与 `ai_generation_stages.active_attempt_id` 不再并存两套状态。
- 旧独立执行记录不再可读。按 ADR 0014，v1 只支持空库初始化，受支持部署不会丢失数据；历史记录不迁移。
- 删除的 HTTP 路由不再返回 404 以外的结果，Studio 不再调用它们。Worker 协议中未使用的快照字段不再被接受或回传。
- `service-sql-allowlist.json`、数据库结构和生成链文档同步移除 standalone 条目。

## 验证

- 控制面全量检查（ruff、format、mypy、pytest）覆盖任务创建、辅助派发、生成链、Worker 协议和架构分层。
- 根一致性测试继续检查四个 Worker 的领取、租约和状态词汇。
- AI Worker 与 Studio 的检查在各项目的验证入口执行。

## 备选方案

- **保留服务层作为历史读取路径**：没有受支持的数据，且会继续维持两套状态表达，不采用。
- **先迁移历史记录再删除**：v1 没有存量数据，迁移成本没有收益，不采用。
