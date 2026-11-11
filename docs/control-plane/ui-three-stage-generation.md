# UI 用例三阶段生成与审核

新建 UI 生成运行以仓库画像成功版本冻结的前端仓库源码和当前需求下选中的正式功能用例为输入，依次生成元素控件清单 JSON、UI 用例设计 JSON 和最终 YAML。仓库画像版本是硬前置；UI 测试分组是唯一入口，画像卡片只读。每阶段必须人工审核；界面默认展示结构化可视化，并可在标题栏切换 JSON/YAML 原文，修改在原文视图完成。

## 使用流程

1. 先完成需求理解并绑定代码仓库，运行仓库画像产生成功版本。在 UI 测试分组选择画像版本（默认最新成功版本，可切换历史版本）、前端仓库（画像识别出多个 `frontend/fullstack` 仓库时必须确认一个）、commit 模式（`profile` 默认使用画像 commit，`latest` 启动时解析分支最新 HEAD）、来源功能用例（默认全选，可筛选调整）和本人的模型连接。没有成功画像版本、没有前端仓库、所选仓库缺少本人的 GitLab 授权或 commit 不可用时阻止启动。
2. 审核第一阶段 JSON，可保存修改或输入指令继续优化。审核通过后，选择本人的模型连接，才会派发第二阶段。
3. 审核第二阶段 JSON。缺定位、缺测试数据不构成剔除理由；只按执行器的操作、断言能力判断可保留内容。否定型预期（如“未出现校验提示”）按 `absent` 保留，并在第三阶段落成 `assert_hidden`。审核通过才派发第三阶段。
4. 在第三阶段审核原格式 YAML 的 stepsJson 和 missingFields，可在原文编辑器修改产物。核查已知字段、数据缺口及定位缺口，补齐后批准 YAML，再导入正式 UI 套件。未处理的 missingFields 会阻止导入。

阶段支持拒绝、继续优化和失败重试。继续优化只重做当前阶段，沿用已经确认的上游产物。查看上游阶段时只读；切换、关闭弹窗前需要处理未保存的修改。

`missingFields` 是草稿的一部分，每条记录包含 `fields`、`operation`、`target`、`value`、`reason`。具体补齐约定见 [UI YAML 人工补全](ui-yaml-completion.md)。新生成结果使用原始格式，不提供数据补全表单。生成侧支持来源明确的变量引用与 `saveTo`；运行期环境变量、后置提取与写回协议见 [UI 环境变量与后置提取](ui-environment-variables.md)。

## 源码配置与来源检查

- `GET /v1/requirements/{id}/generation/ui/source-options` 返回成功画像版本列表和每个仓库的安全投影：`repositoryId`、`pathWithNamespace`、`role`、`confidence`、`responsibilitySummary`、`keyPaths`、`branch`、`commit`、`isFrontend`、`available`、`profileError`，以及 `defaultProfileVersionId` 和 `defaultRepositoryId`。读取入口不访问 GitLab，可用性只反映画像冻结快照。
- `POST /v1/requirements/{id}/generation/ui/source-check` 用当前操作人的个人 GitLab 连接解析分支最新 HEAD，返回 `pinnedCommit`、`currentCommit`、`branch` 和 `changed`；只提示差异，不修改已启动运行。
- `POST /v1/requirements/{id}/generation/ui/stages/ui_surface/run` 新增 `sourceProfileVersionId`（必填）、`sourceRepositoryId`（必填）、`sourceCommitMode`（`profile` 默认 / `latest`）和可选 `gitlabConnectionId`；保留 `functionCaseIds`、`refreshInputs`、`connectionId` 和 `requestId`。`ui_design`、`ui_yaml` 不接受源码字段。
- 首次生成使用所选配置；已有运行上更换输入必须提交 `refreshInputs: true`，从首阶段创建新的 `uiSourceBatchId` 并作废旧批次仍在执行的下游阶段，已通过版本保留。

## 阶段协议

| 阶段 | 默认技能 | 产物 | 停止位置 |
| --- | --- | --- | --- |
| `ui_surface` | `extract-ui-test-surface` | `configJson.uiSurface`，`ui_test_surface/1.0` | `waiting_review` |
| `ui_design` | `map-functional-cases-to-ui-scenarios` | `configJson.uiDesign`，`ui_test_scenarios/2.0` | `waiting_review` |
| `ui_yaml` | `generate-ui-test-case` | `resultYaml`，UI 用例列表 | 生成成功，整体审核仍为 `pending` |

首阶段启动时校验画像版本属于当前需求且为成功版本，所选仓库存在于该版本且角色为 `frontend/fullstack`，来源 binding 有分支、`headCommit`、`cloneUrl` 且没有 `profileError`；随后使用 UI 发起人的个人 GitLab 连接重新解析仓库访问权限。`profile` 模式冻结画像的 `headCommit`，`latest` 模式解析分支最新 HEAD，二者都写入具体 commit SHA。新运行快照包含 `sourceKind: repository`、`sourceProfileVersionId`、`sourceProfileVersionNo`、`sourceRepository`（仓库、分支、commit 模式、实际冻结 commit、解析时间）、仅含所选仓库的 `bindings`、`functionalCases`、`uiWorkflowVersion: ui_three_stage/1.0` 和新的 `uiSourceBatchId`。`bindings` 中的 `cloneUrl`、`connectionId` 只用于 Worker 凭据和回传授权，不进入浏览器响应；`gitlabCredentialsUrl` 由派发载荷按本次 Worker 任务注入，不落库。

正式用例的标题、前置条件、步骤和预期冻结在启动事务内，后续编辑正式用例不改变本次输入。显式选择为空、重复 ID、其他需求的用例均拒绝。未传选择列表的旧客户端默认采用当前需求全部正式用例。新运行固定 `checkpointEnabled: true`。冻结的 pin 是画像版本的副本，不引用画像执行记录；`ui_design` 和 `ui_yaml` 复制首阶段快照，不重新解析画像或 commit。三个阶段的技能与 Worker 只使用冻结的仓库源码、正式功能用例和已审核阶段产物，不读取需求正文或需求理解版本；画像正文、摘要和证据不进入生成 prompt，`sourceContent` 保持为空。

UI 三个阶段各自归属稳定阶段和独立尝试。审核通过先提交本阶段版本，再按需派发下一阶段；后续派发失败不会回滚已通过版本。Worker 每次只获取、执行当前阶段默认技能；两个独立 AI Worker 均支持相同协议。仓库 pin 和正式用例在首阶段冻结，Worker 的 `gitlabCredentialsUrl` 按当前 dispatch 刷新，快照不保存凭据。修订和重试保持尝试身份隔离，旧 Worker 回传不能覆盖新尝试；失败不能清空已确认产物。

第一阶段由调用方指定 workspace 内的 `outputPath`，Worker 优先读取固定路径上的 JSON 文件并完整校验；文件不存在时兼容直接 JSON。不得跟随其他路径或符号链接。

第二阶段按功能用例 `module` 分组，每个模块为一个完整批次，不再按用例条数、步骤数或字符数拆分。模块及模块内用例保留首次出现顺序；缺少模块的用例归入“未分组”。大模块仍可能触发模型输出上限，截断时明确失败，不静默删减或再次拆批。每批使用独立会话标识，携带本批原始用例、对应当前设计（继续优化时）、统一能力约束及已审核元素图。仅检查范围中的用例 ID 随批次裁剪，元素间引用保持完整。

第二阶段不传 `outputPath`，模型直接返回本批完整 JSON，文件回执不能作为成功产物。每次生成和修复都注入完整 JSON Schema。Worker 依次执行严格 JSON 解析、字段类型/枚举、原文一致性和业务覆盖校验；拒绝重复字段、NaN/Infinity、漏用例、重复用例或混入其他批次用例。每批最多自动修复两次，已通过批次不因其他批次修复而重新生成；任一批失败则停止，不发布部分结果。原始回复与校验错误按 `diagnostics/ui_design/batch-NNN` 保存。诊断记录不作为后续 dispatch 的自动恢复缓存。

所有批次通过后再对完整输入校验合并结果，并恢复原始选择顺序，统一进入第二阶段人工审核。进度包含 `batch`、`batchCount`、`completedCases` 和修复次数。模型调用失败不按内容错误重试；模型报告截断时失败，不能接受残缺 JSON。Schema 保留 v2 描述性扩展字段，执行绑定仍限制在第三阶段；控制面接口、产物版本和人工审核门禁不变。

第三阶段也按原始功能用例的模块分批，每模块一个完整批次。输入包含本模块的原始用例、已审核设计、完整元素引用图、源码目录和执行上下文；继续优化时只附带本模块现有 YAML。每批直接返回 YAML list，名称和顺序对应 `batch.expectedCaseNames` 中的保留设计，模块内用例编号及每条用例的步骤编号均从 1 开始。

Worker 对每批执行平台 YAML 草稿校验和用例范围检查，最多修复两次，已经通过的模块保持不变。`missingFields` 的合法缺口可以进入草稿，未知定位或数据不应导致删除用例。仅 `coverage: excluded` 的设计不生成 YAML；整个模块均已排除时跳过模型调用。未排除用例必须有步骤。各批全部成功后按原选中用例顺序合并、统一重排用例编号，再执行完整校验，作为单份 `resultYaml` 回传。诊断按 `diagnostics/ui_yaml/batch-NNN` 保存，进度含模块名、批次及完成数量。结构与范围校验不等于证明所有业务断言语义或实时定位正确，仍需人工审核。

第三阶段名称保留已审核设计，便于在不扩展正式 YAML 字段的前提下核对来源范围。继续优化时也检查当前 YAML 与设计的名称、数量及顺序，不把无法对应的旧草稿任意分派到模块。最终运行生成成功但审核状态仍为 pending，不自动导入或执行。

控制面和 Worker 都校验 JSON 版本、原用例覆盖和已确认的上游内容。YAML 草稿允许明确声明的缺失字段，正式导入使用完整 UI 导入校验。第一、二步不允许直接回传最终成功以跳过审核。

## HTTP 接口

以下接口位于 `/v1/ui-case-generate-task-runs/{runId}`，复用现有项目权限、个人模型授权和响应格式。

| 方法与后缀 | 操作 | 关键字段 |
| --- | --- | --- |
| `PATCH /stage-output` | 保存当前产物 | `stage`；JSON 使用 `configJson` 中唯一当前字段，YAML 使用 `resultYaml` |
| `POST /review-stage` | 批准或拒绝 | `stage`、`action: approve/reject`、可选 `reviewComment`；推进阶段可选 `llmConnectionId` |
| `POST /revise-stage` | 当前阶段继续优化 | `stage`、`revisionInstruction`、当前产物、可选 `llmConnectionId` |
| `POST /retry-stage` | 失败重试 | `stage`、可选 `llmConnectionId` |

需求关联任务通过 `POST /v1/requirements/{requirementId}/generation/ui/stages/ui_surface/run` 启动，携带画像版本、前端仓库、commit 模式并可选 `functionCaseIds` 冻结选中的正式用例；旧需求关联启动入口引导到阶段链。保存要求写权限，审核要求审核权限，修订和重试要求执行权限；模型连接必须属于本次操作者。

## 兼容与运维

审核通过的最终阶段内容可独立导入，不要求补造缺失的上游审核版本。默认技能继续通过统一 S3 文件生命周期维护，发布命令见 [默认技能维护](skills.md)。不要将技能实验目录一并发布。

UI 生成不再上传源码 ZIP，也不再调用源码包上传和 Worker 归档下载接口；`ui_source_archive` 用途、`ai_generate_task_source_archives` 表和旧 ZIP 生成记录已删除，正式 UI 套件/用例与 AI 任务壳保留。迁移和清理边界见 [ADR 0011](adr/0011-ui-generation-repository-source.md) 与 [文件存储](file-storage.md)。

本次发布只更新上述三个默认技能，21 个文件从真实 S3 回读核对大小和 SHA-256；其他 11 个默认技能摘要不变。控制面状态流、HTTP 接口、导入门禁、Worker 模型替身回归及 Studio 原文审核均已覆盖。浏览器使用实际组件与 CodeMirror 检查桌面、窄屏 JSON/YAML；该检查未调用真实模型，也不代表已对业务站点执行 UI 自动化。

第三阶段恢复原始用例、stepsJson 与 missingFields 格式，参见 [UI YAML 待补内容](ui-yaml-completion.md)。历史扩展产物保留兼容读取；新生成结果不再包含数据对象、绑定模板、来源引用或设计冲突字段。

## 第三阶段辅助复核

确定性 YAML/字段/范围校验继续阻断生成，AI 语义复核改为辅助人工审核。两个 Worker 先完成全部模块及合并硬校验，将完整草稿保存到私有诊断目录，再进行每模块最多 120 秒的复核；报告格式最多修复一次。复核问题不触发重生成，复核调用失败也不丢弃草稿。生成结果仍为 success、人工审核仍为 pending。进程终止或用户取消不是复核降级成功；完成前的诊断文件不是平台已发布产物。

`resultSummaryJson.uiSemanticReview` 是可选附属报告，包含 `status`（completed/incomplete）、`artifactSha256` 和 `modules`。每个模块记录名称、批次、状态、errorCode 和 issues；意见包含合并后的 caseIndex、stepIndex、caseId、caseName、code、evidence、repair。未完成原因使用 timeout/model_error/invalid_report/truncated，不回传模型异常原文。旧运行没有此报告时沿用原展示。

控制面按当前 resultYaml 的 UTF-8 SHA-256 判断报告是否过期，读取时输出 stale，不改写历史报告。前端未保存修改同样标记过期。人工可以查看证据，将单条意见带入现有继续优化；这仍是用户主动发起的完整阶段修订，沿用本人模型授权。未新增独立复核重试或跨阶段退回入口。最终批准与正式导入分开，missingFields 未补齐仍禁止导入。
