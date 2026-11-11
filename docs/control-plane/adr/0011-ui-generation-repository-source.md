# UI 生成改用仓库画像版本作为源码来源

2026-11-09。UI 用例生成不再接收人工上传的源码 ZIP，改以仓库画像成功版本中冻结的前端仓库和 commit 作为源码输入。画像是硬前置；UI 发起人必须自行选择画像版本、前端仓库、commit 模式和来源正式功能用例。仓库 pin 在首阶段启动事务内复制并冻结，后续阶段不再重新解析画像或 GitLab。

## 决策

- **画像版本是硬前置**：只有成功的仓库画像版本可作为来源，失败或运行中的画像不形成版本。没有成功版本时阻止启动并引导先生成画像；仓库画像卡片保持只读，UI 测试分组是唯一生成入口。画像版本没有人工审核语义，不能作为生成链上的可审核阶段。
- **源码输入**：`ui_surface` 首阶段的输入是「一个画像版本 pin 的前端仓库 + 当前需求下的正式功能用例」。整个仓库检出后作为三阶段共用的单一 `sourceRoot`，不做 appRoot 裁剪或 sparse checkout；一次运行只支持一个仓库、一个源码根。需求跨多个前端应用时按应用拆成多次生成。
- **用户选择**：画像版本默认最新成功版本，可切换历史版本；前端仓库从画像的 `frontend/fullstack` 角色中确认一个，多个候选时必须选择，没有任何前端仓库时阻止并提示检查仓库绑定或重跑画像；commit 模式为 `profile`（默认，使用画像冻结的 `headCommit`）或 `latest`（启动时解析分支最新 HEAD）。`profile` 模式下 commit 已丢失时明确失败，提示切换最新 HEAD 或重跑画像。
- **启动冻结**：首阶段在 `source` / `source_snapshot_json` 中写入 `sourceKind=repository`、`sourceProfileVersionId`、`sourceProfileVersionNo`、`sourceRepository`（仓库、分支、commit 模式、实际冻结 commit、解析时间）、仅含所选仓库的 `bindings`、`functionalCases`、`uiWorkflowVersion` 和新的 `uiSourceBatchId`。冻结的是 pin 副本，不引用画像执行记录；后续阶段复制首阶段快照。`refreshInputs` 创建新批次并作废旧批次仍在执行的下游阶段，已通过版本保留。
- **授权**：始终使用 **UI 发起人** 的 GitLab 个人连接重新校验仓库访问权限，不使用画像发起人的连接，也不因画像发起人可用而回退。派发载荷按本次 Worker 任务注入 `gitlabCredentialsUrl`；clone URL、`connectionId`、token 和 `gitlabCredentialsUrl` 不进入浏览器响应，也不落库到快照。
- **Worker 获取源码**：Worker 只读取一个 binding，按 `gitlabCredentialsUrl` 获取凭据，通过 askpass 临时注入，`--filter=blob:none --no-checkout` clone 后 fetch 分支和精确 commit，detached checkout 并校验 HEAD，最后删除 `.git`，避免模型读取对象库。成功后清理工作区，失败按配置保留诊断工作区；git 超时、仓库大小和文件数超限时明确失败。
- **画像内容不进入生成**：画像输出只用于定位仓库、分支和 commit，以及展示来源追溯；画像正文、摘要和证据不注入 UI 生成 prompt，UI 阶段也不读取需求理解正文。
- **来源漂移**：正式功能用例变化沿用现有数据库比较并在链详情返回 `sourceChanged`；分支 commit 漂移不在每次链详情读取时请求 GitLab，而由 `POST /v1/requirements/{id}/generation/ui/source-check` 显式检查。发现差异只提示切换最新 HEAD 或重跑画像，不自动改变已冻结的运行输入。
- **ZIP 退役**：新运行不接受源码 ZIP，`PUT /v1/ui-case-generate-tasks/{taskId}/source-archive`、`GET /internal/ai-worker/tasks/{taskId}/source-archive`、`ui_source_archive` 文件用途、控制面归档服务、Worker 归档下载和 Studio 上传入口均已删除。
- **旧数据清理边界（已执行）**：按任务事务删除 ZIP 来源的生成记录（`ai_generate_version_imports`、`ai_generate_stage_versions`、`ai_generation_attempts`、`ai_generation_stages`、`ai_generate_task_source_archives`）及 S3 中的 `ui_source_archive` 对象；保留正式 `ui_test_suites` / `ui_test_cases` 和 `ai_generate_tasks` 的 UI 任务壳，避免需求上的 UI 配置指针失效；允许 `effective_import_id` 悬空并按现有正式资产规则展示。2026-11-09 已备份数据库、核对 dry-run 后执行 apply，并从 Alembic 基线删除源码包表。

## 接口与快照

- `GET /v1/requirements/{id}/generation/ui/source-options`：返回成功画像版本列表、每个仓库的安全投影（仓库 ID、路径、角色、置信度、职责摘要、关键目录、分支、commit、是否前端、是否可用、画像错误）及默认画像版本和默认仓库；读取时不请求 GitLab，可用性只反映画像冻结快照。
- `POST /v1/requirements/{id}/generation/ui/source-check`：用当前操作人的 GitLab 连接解析分支最新 HEAD，返回 `pinnedCommit`、`currentCommit`、`branch` 和 `changed`，不改变已有运行。
- `POST /v1/requirements/{id}/generation/ui/stages/ui_surface/run` 新增 `sourceProfileVersionId`（必填）、`sourceRepositoryId`（必填）、`sourceCommitMode`（`profile` 默认 / `latest`）和可选 `gitlabConnectionId`；保留 `functionCaseIds`、`refreshInputs`、`connectionId`、`requestId`。`ui_design` 和 `ui_yaml` 拒绝源码字段，继续使用首阶段快照和上游版本。

## 后果

- UI 生成不再依赖人工维护的源码包，画像识别出的前端仓库和 commit 直接成为可追溯输入；来源身份统一为仓库、分支、commit、画像版本和正式用例。
- 运行可复现性提高：`latest` 也在启动时冻结为具体 SHA，分支前进不会改变已启动运行。
- 代价是启动依赖 GitLab 可达性和 UI 发起人的个人授权；大仓库 clone 有时间和容量成本，需要超时、大小/文件数限制及工作区清理策略。
- 画像角色误判由用户确认仓库兜底；多前端应用不在第一版覆盖范围。
- ZIP 清理不可逆，必须先备份数据库和对象清单并完成 dry-run；2026-11-09 已完成清理，回滚只能依赖备份恢复。

## 拒绝的替代方案

- **保留 ZIP，画像只做推荐**：仍需维护可能过期的源码包，且无法把画像识别的 commit 作为单一事实来源。
- **使用画像发起人的 GitLab 连接**：跨用户运行会借用他人授权，违背个人授权边界；发起人无权限时应明确失败。
- **运行只引用画像执行记录**：画像运行记录被删除或后续画像重跑会改变已有运行的输入，无法保证冻结；因此复制 pin。
- **把画像正文注入 prompt**：画像摘要是模型推断结果，可能误导源码分析；UI 生成需要的只是仓库和 commit。
- **自动在每次读取链详情时解析最新 HEAD**：会给每个查看者触发 GitLab 请求，并使来源状态不稳定；改为显式 `source-check`。
- **一次运行支持多个仓库或多个源码根**：扩大定位和跨应用歧义，第一版按应用拆多次生成。
- **保留 ZIP 作为长期兜底**：会形成第二条新运行路径，与仓库来源的授权、快照和清理规则分叉；灰度期只保留临时开关，清理后删除兼容代码。

相关文档：[UI 用例三阶段生成与审核](../ui-three-stage-generation.md)、[生成链、阶段版本与正式资产导入](../generation-chain.md)、[统一 S3 文件存储](../file-storage.md)、[AI Worker 上下文](../../ai-worker/CONTEXT.md)、[仓库画像分析](../../ai-worker/repository-profile.md)、[Studio 上下文](../../studio/CONTEXT.md)。
