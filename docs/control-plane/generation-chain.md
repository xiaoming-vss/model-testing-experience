# 需求生成链、阶段版本与正式资产导入

一条需求 + 一种生成类型对应一条生成链，链内阶段有草稿和审核通过版本。旧任务/运行 URL 与 Worker 协议继续可用；新界面通过需求维度的 `/generation` 接口读写。

## 版本与草稿

- `ai_generate_tasks` 是链容器；`ai_generate_run_stages` / `ai_generate_stage_attempts` 继续保存草稿、生成记录和运行状态。
- `ai_generate_stage_versions` 只在审核通过时写入，保存产物正文快照、格式、审核信息和生成时读取的上游版本映射。版本按 `(task_id, stage)` 独立编号。
- 最新版本按版本号最大；不存在主线或“设为当前”。下游默认读取上游最新已通过版本，也允许手动选择历史版本，审核通过后在版本上记录 `based_on_old`。
- 历史迁移版本的上游映射为 `null` 时，版本详情按该版本审核时间（缺省取创建时间）解析当时已通过的最新上游，与历史导入父链的兼容规则一致；这是历史推定，不回写版本快照，也不取当前最新版本。已记录的上游 ID 即使已删除也保留在详情映射中，供界面显示“上游已删除”。
- 草稿依赖的上游版本被硬删除时，不删除其生成尝试，而在尝试上写 `invalidated_at` / `invalidated_reason`。作废草稿保留用于诊断，但不再计入待审核草稿，不能审核或继续优化；界面提示后只能重新生成。
- 草稿只取阶段的当前产物尝试，且该阶段审核状态为待审核、尝试尚无版本。审核不通过即丢弃当前候选，界面回到已有已通过版本（没有历史版本则回到未生成），不保留“已丢弃”标签或提示，不返回草稿、不计入待审核、不创建已通过版本；正文与审核记录保留于尝试账本，拒绝意见、审核人和时间记录于该尝试的 `progress_json.candidateReview`；丢弃标记沿用 `invalidated_at` / `invalidated_reason`，重新生成不继承该审核记录。已退回的历史草稿按相同规则读取，无需迁移。丢弃后可重新生成，不能再审核或继续优化该候选；已通过历史版本不受影响。继续优化或重跑取代的旧尝试保留在尝试账本中用于诊断，不再视为草稿，也不计入待审核草稿。已通过但尚未写入版本的当前产物仍作为草稿展示，供崩溃恢复或版本删除后重新审核。
- `busy` 只表示链上存在执行中的运行；待审核草稿由 `draftCount` 单独表达。审核、继续优化和版本导入不因存在草稿而禁用；启动或重新运行阶段只检查本阶段是否已有待审核草稿，其他阶段的草稿不阻塞。

## 接口

| 接口 | 行为 |
| --- | --- |
| GET `/v1/requirements/{id}/generation` | 四条链的全景：阶段、最新版本、草稿、运行状态、叶子导入状态 |
| GET `/v1/requirements/{id}/generation/{kind}` | 单条链详情，草稿正文只在此返回 |
| GET `/.../generation/{kind}/versions/{versionId}` | 已通过版本内容、审核信息和父链摘要 |
| POST `/.../generation/{kind}/stages/{stage}/run` | 单步生成；可指定上游版本 |
| POST `/.../generation/{kind}/stages/{stage}/revision` | 继续优化当前草稿 |
| POST `/.../generation/{kind}/stages/{stage}/review` | approve / reject；approve 可暂停或继续；Studio 不提供审核备注输入，旧请求的可选备注保持兼容 |
| DELETE `/.../generation/{kind}/versions/{versionId}` | 硬删除版本，并作废依赖草稿 |
| GET `/.../generation/{kind}/versions/{versionId}/import-options` | 叶子版本完整父链、正式目标和当前正式来源 |
| POST `/.../generation/{kind}/versions/{versionId}/import` | 按叶子版本导入；冲突预览与覆盖确认沿用原导入器 |

审核通过但进程在写入版本前退出时，再次审核会按来源尝试补写版本，避免同一草稿生成两个版本。同一链同时只允许一个执行中运行；待审核草稿按阶段独立，重跑或继续优化只作用于当前阶段，其他阶段的草稿保持不动。

## 阶段产物与执行输入隔离

有人工检查点的运行中，每次派发只拥有当前阶段的产物写权限。载荷中的其他阶段字段属于已选择的上游输入快照，可能是旧的已通过版本，不能据此创建前序编辑尝试、移动前序产物指针或改变前序待审核正文。审核通过并继续时，显式审核的阶段仍可保存本次人工审核内容；无检查点的自动流水线继续允许同一次派发产出多个阶段。

各阶段的候选、审核和版本独立。运行时才选择上游已通过版本，并将实际内容、版本编号和本次指令与队列尝试在同一事务冻结；缺少已通过上游时拒绝派发。继续优化沿用该阶段原尝试的输入快照并叠加自身产物，不从整条链的当前投影重建输入。失败重试继续使用原尝试快照。明确记录为空的上游映射不再用后来的版本补齐；只有缺少记录的历史尝试兼容按创建时间解析。

审核通过并继续先保存当前阶段版本，再经过统一的阶段运行入口选择并冻结下一阶段输入。后续阶段运行期间，前序候选可以单独通过或删除，其审核不能改动正在运行阶段的状态、调度指针或输入；继续优化和继续派发仍受现有单链执行限制。Studio 分开处理操作提交中与链执行中，只有目标阶段正在执行时才禁用其单独审核。

`services/ai_execution/__init__.py` 在写入边界执行该限制。回归覆盖前序新候选待审核、下游使用旧的已通过版本时的派发、运行及完成，以及材料提取到需求理解的真实阶段链。

## 正式资产导入来源

`ai_generate_version_imports` 每个受影响的正式目标一行，保存：

- 叶子版本 `version_id` 和叶子阶段；
- 完整父链 `parent_versions_json`（所有上游阶段，不只直接上游）；
- 本次新增或覆盖的正式用例 ID `changed_case_ids_json`；
- 目标类型/目标 ID、导入前后的目标用例总数、是否混合来源、导入人和时间、叶子版本审核快照。

正式目标表 `function_test_suites`、`api_collections`、`ui_test_suites` 增加 `effective_import_id`，指向最近一次成功导入。导入前会校验叶子版本的所有父版本仍存在且阶段匹配；引用已删除上游版本的版本不能导入。功能导入按模块自动创建/复用测试集；API 和 UI 导入必须选择当前需求下的正式目标。

导入仍复用现有冲突预览、覆盖确认和用例编号规则。导入器额外返回每个目标的 `changedCaseIds`；适配层在一个事务里写导入记录并更新目标指针。删除版本时同时删除其导入记录，正式资产和 `effective_import_id` 保留为悬空指针；生成链导入选项据此提示来源已删除，正式资产本身不受影响。

## 正式读取边界

导入完成后，正式资产是独立的测试资源，不反向关联生成链版本。正式读取方（功能测试集、API 集合、UI 测试套件、迭代看板、测试报告）不解析 `effective_import_id`，也不展示来源版本或“来源已删除”。看板按当前迭代关联的用例统计。

生成链自身仍保留 `effective_import_id` 和导入记录：导入选项读取它判断目标是否已导入、展示本次导入后的版本指针，并阻止同一版本重复导入。删除版本后指针保留为悬空值，生成链据此提示需要重新导入；正式用例不受影响。

## UI 生成输入与来源追溯

UI 生成以源码 ZIP 和当前需求下的正式功能用例为输入。Studio 首次生成复用功能用例选择器，默认全选，允许按测试集和标题筛选后调整范围；后端验证非空、不重复及需求归属，并将用例原文、源码文件身份、文件名、大小及摘要冻结进运行快照。

首阶段运行请求支持可选 `functionCaseIds` 与 `refreshInputs`（默认 `false`）。旧请求省略用例编号时仍读取当前需求全部正式功能用例。普通重跑沿用运行快照；已有运行上更换输入必须在 `ui_surface` 阶段明确提交 `refreshInputs: true`，从首阶段创建新运行。执行中的链不能更换输入，`requestId` 用于重复提交去重。

更换输入会保留已通过版本，将旧运行未版本化的尝试标记为失效。新运行的 UI 设计和 YAML 仅可使用同一运行审核通过的上游，不能混用上一轮产物；历史版本仍可查看、对比和按已有规则导入。当前源码文件或所选正式用例发生变化时，生成链返回 `sourceChanged`。

详细链、草稿及版本详情的 `sourceInputs` 返回源码元信息与冻结的用例正文，Studio 在来源追溯中展示并支持展开。版本审核时将来源复制进版本上下文，不依赖后来更换的任务配置；历史版本优先兼容读取来源尝试和原运行，未记录的信息显示为未记录。该读取结构不包含 Worker 下载地址或授权材料；概览不重复返回完整用例正文。

回归入口：`tests/test_ui_chain_inputs.py`，以及 Studio 的 `UiGenerationInputsModal.test.tsx`、`RequirementGenerationPanorama.test.tsx`、`UiGenerationCaseSelector.test.tsx`。

## 相关代码与验证

- 服务：`apps/control-plane/src/testing_agent/services/generation_chain.py`
- 查询：`repositories/generation_chain.py`
- 模型：`models/ai_generate_stage_version.py`、`models/ai_generate_version_import.py`
- 迁移：`alembic/versions/20261029_0052_generation_stage_versions.py`、`20261029_0053_generation_import_sources.py`
- 测试：`tests/test_generation_chain.py`、`tests/test_generation_chain_api.py`、`tests/test_generation_stage_version_migration.py`，以及既有功能/API/UI 导入回归
- Studio：`RequirementGenerationPanorama.tsx`、`GenerationChainModal.tsx`、`GenerationChainImportModal.tsx`、`useRequirementGenerationChain.ts`

功能测试首阶段的上游为需求分析链的 `feature_understanding`，沿用 `upstreamVersions` 选择规则：缺省选最新已审核版本，也可手动指定历史版本。首阶段运行及重跑冻结 `sourceContent` 与 `requirementUnderstandingVersion`；后续测试点、完整用例跟随所选测试需求分析版本的输入快照，图谱跟随完整用例运行的冻结输入。版本行保存 `functionalSource`，防止原运行/尝试删除后丢失来源。初始运行、独立任务和旧需求设计运行入口统一经过同一版本解析，不再要求绑定增强文本。历史运行保持既有快照；旧运行若没有版本来源而发起新的下游生成或图谱分析，需先存在已审核需求理解版本。

生成链继续优化请求支持可选 `attachmentFileIds`（默认空列表，最多 6 个）。沿用既有优化附件的项目、上传者、用途、图片格式和大小校验，附件绑定当前运行，元信息只冻结到本轮尝试的 `revisionAttachments`，通过既有 Worker 图片票据获取；下一轮未选择的图片不自动沿用。

## API 测试两阶段生成

需求画布中的新 API 生成运行依次执行「接口配置提取」和「API 用例生成」。前者生成 JSON，审核通过后形成版本；后者选择已审核的提取版本作为冻结输入，生成 YAML，审核通过后可导入。首阶段支持审核通过并继续、重新生成与优化；删除上游版本时沿用依赖草稿作废规则。新运行快照以 `apiWorkflowVersion: api_two_stage/1.0` 区分，旧单阶段运行继续按原协议处理，旧最终版本无需补造不存在的上游版本即可查看和导入。已有旧运行时重新运行提取会创建新运行，保留历史运行。

API 阶段运行的补充指令写入本次派发的输入快照；审核通过并继续时，可在审核请求中通过可选 `instruction` 为下一阶段提供指令。省略时沿用现有空指令行为，不改变旧客户端契约。

API 测试集可以在有写权限的同一项目内调整所属需求；更新接口的可选 `requirementId` 不传或为 `null` 时保留原归属，空字符串无效。目标需求的同名集合会阻止修改。测试集、用例及导入来源记录随集合保留；API 运行历史的需求和迭代字段按集合当前归属解析，变更后历史显示的归属也会随之变化。导入目标列表按当前需求筛选。
