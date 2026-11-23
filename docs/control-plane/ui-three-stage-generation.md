# UI 用例三阶段生成与审核

UI 生成使用当前采用的仓库画像、选定前端仓库和正式功能用例，依次生成元素控件清单、UI 用例设计和 YAML。每阶段可有多个候选、最多一份当前采用内容；试生成可显式选择候选，采用和导入时校验该内容自身的完整冻结来源，不要求上游当前内容一致。详见[需求生成链](generation-chain.md)。

## 使用流程

1. 绑定代码仓库并采用仓库画像，选择前端仓库、commit 模式、正式功能用例和模型连接。默认使用画像冻结的 commit，也可选择启动时的最新 HEAD。
2. 生成并检查元素控件清单、UI 用例设计和 YAML 候选。各阶段可重新生成、手工编辑或优化，也可用前序候选继续试生成。
3. 按来源顺序采用候选；采用后可继续下一阶段。检查 YAML 的 `stepsJson` 和 `missingFields`，补齐缺口并采用后，选择正式 UI 套件预览和确认导入。

切换或关闭时会提示处理未保存修改。`missingFields` 的补齐规则见 [UI YAML 人工补全](ui-yaml-completion.md)，变量和提取规则见 [UI 环境变量与后置提取](ui-environment-variables.md)。

## 源码配置与来源检查

`source-options` 返回当前画像的安全仓库投影；`source-check` 使用操作者的个人 GitLab 连接比较当前分支 HEAD 与固定 commit，不修改既有候选。首阶段将仓库、commit 和所选正式用例冻结到来源快照，后续阶段使用同一来源；重新生成可创建新的输入批次。凭据及内部地址不进入浏览器响应。

## 阶段协议

以下描述 Worker 产物和校验协议；涉及旧版审核或版本的表述以[需求生成链](generation-chain.md)的候选和当前内容规则为准。

| 阶段 | 默认技能 | 产物 | 停止位置 |
| --- | --- | --- | --- |
| `ui_surface` | `mtx-extract-ui-test-surface` | `configJson.uiSurface`，`ui_test_surface/1.0` | `waiting_review` |
| `ui_design` | `mtx-map-functional-cases-to-ui-scenarios` | `configJson.uiDesign`，`ui_test_scenarios/2.0` | `waiting_review` |
| `ui_yaml` | `mtx-generate-ui-test-case` | `resultYaml`，UI 用例列表 | 生成成功，整体审核仍为 `pending` |

部署时先同步表中的三个默认技能，再切换 AI Worker。独立 UI 用例生成也使用 `mtx-generate-ui-test-case`。

首阶段启动时要求当前需求已采用仓库画像；所选仓库存在于该画像且角色为 `frontend/fullstack`，来源 binding 有分支、`headCommit`、`cloneUrl` 且没有 `profileError`；随后使用 UI 发起人的个人 GitLab 连接重新解析仓库访问权限。`profile` 模式冻结画像的 `headCommit`，`latest` 模式解析分支最新 HEAD，二者都写入具体 commit SHA。新运行快照包含 `sourceKind: repository`、`sourceProfileCandidateId`、`sourceProfileSnapshotId`、`sourceRepository`（仓库、分支、commit 模式、实际冻结 commit、解析时间）、仅含所选仓库的 `bindings`、`functionalCases`、`uiWorkflowVersion: ui_three_stage/1.0` 和新的 `uiSourceBatchId`。`bindings` 中的 `cloneUrl`、`connectionId` 只用于 Worker 凭据和回传授权，不进入浏览器响应；`gitlabCredentialsUrl` 由派发载荷按本次 Worker 任务注入，不落库。

正式用例的标题、前置条件、步骤和预期冻结在启动事务内，后续编辑正式用例不改变本次输入。显式选择为空、重复 ID、其他需求的用例均拒绝。未传选择列表的旧客户端默认采用当前需求全部正式用例。新运行固定 `checkpointEnabled: true`。冻结的 pin 是画像版本的副本，不引用画像执行记录；`ui_design` 和 `ui_yaml` 复制首阶段快照，不重新解析画像或 commit。三个阶段的技能与 Worker 只使用冻结的仓库源码、正式功能用例和已审核阶段产物，不读取需求正文或需求理解版本；画像正文、摘要和证据不进入生成 prompt，`sourceContent` 保持为空。

UI 三个阶段各自归属稳定阶段和独立尝试。采用候选只更新该阶段当前内容，再按需派发下一阶段；后续派发失败不会回滚已采用内容。Worker 每次只获取、执行当前阶段默认技能；两个独立 AI Worker 均支持相同协议。仓库 pin 和正式用例在首阶段冻结，Worker 的 `gitlabCredentialsUrl` 按当前 dispatch 刷新，快照不保存凭据。修订和重试保持尝试身份隔离，旧 Worker 回传不能覆盖新尝试；失败不能清空已确认产物。

第一阶段由调用方指定 workspace 内的 `outputPath`，Worker 优先读取固定路径上的 JSON 文件并完整校验；文件不存在时兼容直接 JSON。不得跟随其他路径或符号链接。

第二阶段按功能用例 `module` 分组，每个模块为一个完整批次，不再按用例条数、步骤数或字符数拆分。模块及模块内用例保留首次出现顺序；缺少模块的用例归入“未分组”。大模块仍可能触发模型输出上限，截断时明确失败，不静默删减或再次拆批。每批使用独立会话标识，携带本批原始用例、对应当前设计（继续优化时）、统一能力约束及已审核元素图。仅检查范围中的用例 ID 随批次裁剪，元素间引用保持完整。

第二阶段不传 `outputPath`，模型直接返回本批完整 JSON，文件回执不能作为成功产物。每次生成和修复都注入完整 JSON Schema。Worker 依次执行严格 JSON 解析、字段类型/枚举、原文一致性和业务覆盖校验；拒绝重复字段、NaN/Infinity、漏用例、重复用例或混入其他批次用例。每批最多自动修复两次，已通过批次不因其他批次修复而重新生成；任一批失败则停止，不发布部分结果。原始回复与校验错误按 `diagnostics/ui_design/batch-NNN` 保存。诊断记录不作为后续 dispatch 的自动恢复缓存。

所有批次通过后再对完整输入校验合并结果，并恢复原始选择顺序，统一进入第二阶段人工审核。进度包含 `batch`、`batchCount`、`completedCases` 和修复次数。模型调用失败不按内容错误重试；模型报告截断时失败，不能接受残缺 JSON。Schema 保留 v2 描述性扩展字段，执行绑定仍限制在第三阶段；控制面接口、产物版本和人工审核门禁不变。

第三阶段也按原始功能用例的模块分批，每模块一个完整批次。输入包含本模块的原始用例、已审核设计、完整元素引用图、源码目录和执行上下文；继续优化时只附带本模块现有 YAML。每批直接返回 YAML list，名称和顺序对应 `batch.expectedCaseNames` 中的保留设计，模块内用例编号及每条用例的步骤编号均从 1 开始。

Worker 对每批执行平台 YAML 草稿校验和用例范围检查，最多修复两次，已经通过的模块保持不变。`missingFields` 的合法缺口可以进入草稿，未知定位或数据不应导致删除用例。仅 `coverage: excluded` 的设计不生成 YAML；整个模块均已排除时跳过模型调用。未排除用例必须有步骤。各批全部成功后按原选中用例顺序合并、统一重排用例编号，再执行完整校验，作为单份 `resultYaml` 回传。诊断按 `diagnostics/ui_yaml/batch-NNN` 保存，进度含模块名、批次及完成数量。结构与范围校验不等于证明所有业务断言语义或实时定位正确，仍需人工审核。

第三阶段名称保留已审核设计，便于在不扩展正式 YAML 字段的前提下核对来源范围。继续优化时也检查当前 YAML 与设计的名称、数量及顺序，不把无法对应的旧草稿任意分派到模块。最终运行生成成功但审核状态仍为 pending，不自动导入或执行。

控制面和 Worker 都校验 JSON 版本、原用例覆盖和已确认的上游内容。YAML 草稿允许明确声明的缺失字段，正式导入使用完整 UI 导入校验。第一、二步不允许直接回传最终成功以跳过审核。

## HTTP 接口

UI 候选生成、采用和正式导入使用需求生成链接口，入口和来源校验见[需求生成链](generation-chain.md#接口)。首阶段通过 `candidate-run` 指定前端仓库、commit 模式和选中的功能用例；下游阶段可选择候选进行试生成。采用和导入前校验整条来源与当前采用内容一致。

## 兼容与运维

已采用的最终阶段当前内容可独立导入，不要求补造缺失的上游采用内容。默认技能继续通过统一 S3 文件生命周期维护，发布命令见 [默认技能维护](skills.md)。不要将技能实验目录一并发布。

UI 生成不再上传源码 ZIP，也不再调用源码包上传和 Worker 归档下载接口；`ui_source_archive` 用途、`ai_generate_task_source_archives` 表和旧 ZIP 生成记录已删除，正式 UI 套件/用例与 AI 任务壳保留。迁移和清理边界见 [ADR 0011](adr/0011-ui-generation-repository-source.md) 与 [文件存储](file-storage.md)。

本次发布只更新上述三个默认技能，21 个文件从真实 S3 回读核对大小和 SHA-256；其他 11 个默认技能摘要不变。控制面状态流、HTTP 接口、导入门禁、Worker 模型替身回归及 Studio 原文审核均已覆盖。浏览器使用实际组件与 CodeMirror 检查桌面、窄屏 JSON/YAML；该检查未调用真实模型，也不代表已对业务站点执行 UI 自动化。

第三阶段恢复原始用例、stepsJson 与 missingFields 格式，参见 [UI YAML 待补内容](ui-yaml-completion.md)。历史扩展产物保留兼容读取；新生成结果不再包含数据对象、绑定模板、来源引用或设计冲突字段。

## 第三阶段辅助复核

确定性 YAML/字段/范围校验继续阻断生成，AI 语义复核改为辅助人工审核。两个 Worker 先完成全部模块及合并硬校验，将完整草稿保存到私有诊断目录，再进行每模块最多 120 秒的复核；报告格式最多修复一次。复核问题不触发重生成，复核调用失败也不丢弃草稿。生成结果仍为 success、人工审核仍为 pending。进程终止或用户取消不是复核降级成功；完成前的诊断文件不是平台已发布产物。

`resultSummaryJson.uiSemanticReview` 是可选附属报告，包含 `status`（completed/incomplete）、`artifactSha256` 和 `modules`。每个模块记录名称、批次、状态、errorCode 和 issues；意见包含合并后的 caseIndex、stepIndex、caseId、caseName、code、evidence、repair。未完成原因使用 timeout/model_error/invalid_report/truncated，不回传模型异常原文。旧运行没有此报告时沿用原展示。

控制面按当前 resultYaml 的 UTF-8 SHA-256 判断报告是否过期，读取时输出 stale，不改写历史报告。前端未保存修改同样标记过期。人工可以查看证据，将单条意见带入现有继续优化；这仍是用户主动发起的完整阶段修订，沿用本人模型授权。未新增独立复核重试或跨阶段退回入口。最终批准与正式导入分开，missingFields 未补齐仍禁止导入。
