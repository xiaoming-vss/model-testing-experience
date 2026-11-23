# 生成链多候选与单一当前内容改造方案

- 日期：2026-11-20
- 状态：已确认的实施规格；当前行为以代码和现行文档为准，改造完成前不得视为已上线。
- 负责人：control-plane maintainers
- 来源：2026-11-19 用户确认的生成链改造讨论及本地工作规格。
- 关联规范：[生成链现状](../control-plane/generation-chain.md)、[ADR 0024](../control-plane/adr/0024-generation-candidates-current.md)。
- 目标：每条需求、每种生成类型、每个阶段允许多个候选供比较，但最多一份当前确认内容；默认生成读取当前结果，明确选择的候选允许用于后续试生成，最终采用和导入校验整条来源一致性。
- 涉及项目：control-plane、ai-worker、studio；其余三个 Worker 本轮不做行为改造。
- 优先级：先完成本改造，再重新讨论历史知识库与 RAG。此前讨论的跨需求关联和知识库方案不在本次实施范围，待改造完成后重新设计。
- 本文新增表名、字段名和路径是拟议设计；标明的现有路径已按本轮代码核对。数据库中是否存在重复配置、缺失来源等情况需后续只读盘点，不能从代码推断实际数据数量。

## 1 推荐方案

按用户最新补充，采用“唯一当前链 + 多候选池 + 唯一阶段当前内容 + 来源闭包校验 + 运行审计”的模型。正常生成默认读取当前结果；试生成允许明确选择上游候选，但不改变任何阶段的当前采用结果。旧的任意历史版本选择接口退出，新的候选选择有范围、快照和整条来源校验。

```text
候选 A   候选 B   候选 C
            │
        确认采用 B
            ↓
    唯一当前内容 B → 下游生成与未来知识检索

继续生成 D 不改变当前 B；明确采用 D 后才替换 B。
A/B/C 可以保留供比较，但不会全部进入下游上下文。

材料候选 A → 分析候选 A1 → 测试点候选 A2
材料候选 B → 分析候选 B1 → 测试点候选 B2
可先分别试生成再比较；正式采用按材料→分析→测试点逐级确认一致的分支。
```

业务界面提供候选列表、比较和“确认采用”。原审核动作整合为“审核通过并采用”，一次只采用一个候选。正式资产导入仍是独立动作，只读取当前有效内容。

attemptId、runId、实际输入输出、审核事件与导入回执继续作为审计证据。历史运行本身不能直接用作上游；可用候选经显式选择可以成为试生成输入，只有确认采用后才能成为当前正式输入。

材料、分析、测试点和用例仍是不同阶段产物，每种各有一份当前结果。多候选不意味着要求模型每次同时读取全部候选。

## 2 本轮范围

### 2.1 必须改造

- 四条需求生成链的 11 个业务阶段。
- 需求生成配置任务的当前身份，避免每个任务各有一套“当前内容”。
- 审核、编辑、优化、重跑、审核并继续和正式导入。
- 上下游依赖、来源指纹、当前内容新鲜度和迟到结果处理。
- 候选试生成选择、跨阶段来源闭包、分支一致性与逐级采用校验。
- 当前材料的其他消费方：代码风险、仓库画像、测试单图谱。
- 功能用例派生图谱的源身份。
- 仓库画像的业务版本选择及 UI 源码选择入口。
- 运行历史与导入历史中依赖旧版本表的读取。
- 数据转换、旧接口退出、前端替换与必要回归。

### 2.2 保留且不误删

| 内容 | 保留原因 |
| --- | --- |
| 多个候选 | 可比较并显式用于试生成，不自动进入默认生成或知识检索 |
| AI 执行与尝试身份 | 队列、租约、回传、重试、停止或失效均依赖它们 |
| 实际输入、输出审计快照 | 解释运行与审核过程；不参与默认业务读取 |
| 已创建的测试执行快照 | 编辑用例不能改变过去实际执行的步骤与预期 |
| 正式功能/API/UI 用例 | 独立正式资产，不因生成内容替换或清空而删除 |
| Git commit 与 UI 输入批次 | 保证运行期间源码和输入一致 |
| sourceFormatVersion、schemaVersion、workflowVersion | 它们是协议格式版本，不是用户选择的业务内容版本 |
| 独立任务的检查点和审核流程 | 共用存储和导入表需要适配，但不强行改成需求链 |
| 代码风险、报告、测试单图谱的执行历史 | 属于运行记录，不提供历史业务版本作为新输入 |

本轮不实施 RAG、向量索引、跨需求复用、用例修订版本库或全新测试资产模型。正式用例目前的编辑、身份和执行快照机制继续使用。

## 3 现有机制梳理

### 3.1 数据模型

| 现有对象 | 当前作用 | 本轮处理 |
| --- | --- | --- |
| `ai_generate_tasks` | 生成配置/任务容器；需求链读取通常取对应类型最近任务 | 增加确定的当前链绑定，不继续以创建时间推断当前链 |
| `ai_generation_stages` | `(task_id, stage)` 唯一；有 current_attempt_id、active_attempt_id、review_status、next_version_no；UI 还带输入批次 | 保留阶段身份和运行指针；单个 current_attempt/review_status 不再代表候选池 |
| `ai_generation_attempts` | 生成、修订、人工编辑尝试；冻结输入、输出、错误和失效信息 | 保留为运行/候选记录，审核信息不再依赖版本表判断 |
| `ai_generate_stage_versions` | 审核通过插入不可变正文、递增版本号、上游版本映射和审核信息 | 转换为候选、当前内容及审计后退出旧模型；不丢弃仍需比较的候选正文 |
| `ai_generate_version_imports` | 同时服务阶段版本导入与独立候选导入；有版本/尝试外键、父版本映射及目标变更 | 改为来源自包含的导入回执，解除业务版本外键 |
| 正式目标 `effective_import_id` | 最近一次真实导入的回执指针 | 可以保留，指向新回执；不变成当前生成内容指针 |

当时的关键代码包括[稳定阶段](../../apps/control-plane/src/testing_agent/models/ai_generation_stage.py)、阶段版本（已删除）、[尝试](../../apps/control-plane/src/testing_agent/models/ai_generation_attempt.py)和旧导入记录（已删除）。

### 3.2 当前业务路径

1. 配置入口可以创建新的配置任务；链查询按需求和类型读取最近任务。`ai_generate_tasks` 的业务 ID 唯一不等于 `(requirement_id, kind)` 唯一。
2. 启动阶段调用 `select_upstream_versions`：请求可以指定历史版本，否则按版本号选择最新已审核版本；UI 还限制同输入批次。
3. 当前尝试保存 `versioning.upstreamVersions`、`baseVersionId` 和 `requirementMaterialVersion` 等来源信息。
4. Worker 只消费冻结内容。回传成功产生候选，不自动审核。
5. 审核通过调用 `DirectStageStorage.approve`：新增版本行、递增 next_version_no，将来源和审核信息复制进去。
6. 正式导入按 version_id 找叶子产物，同时读取来源 attempt；变更用例后写版本导入记录。
7. 删除版本会删除关联导入记录并作废依赖草稿；不会删除正式资产，目标指针可能悬空。
8. 当前实现允许下游引用旧的已审核上游；已有下游已审核版本不会因为上游再生成就自动作废。

这些行为曾集中于 `generation_chain.py`、`stage_storage` 及已移除的上游版本选择和版本删除模块；这是改造前的历史记录。

### 3.3 版本机制的额外使用方

- `requirement_material_source.py` 提供“指定或最新材料版本”，被功能生成、仓库画像、代码风险和测试单图谱消费。
- `relations.py` 按已审核完整用例版本找到/生成用例图谱，不能只删除阶段版本读取而遗漏图谱。
- `repository_profile_versions.py` 从成功画像尝试投影出带 vN 的版本列表，并没有另一张专用画像版本表。
- UI 源码配置选择画像版本，冻结仓库 pin 和正式功能用例；画像正文不进入 UI prompt。
- `direct_attempt_history.py` 和 `direct_attempt_view.py` 通过连接版本表判断审核、待导入及已导入，运行历史也会随删表失效。
- 独立生成的导入/删除使用同一张 `ai_generate_version_imports`，不能直接删除该表而不迁移这些调用方。
- Studio 不只展示 vN，还在生成设置、材料选择、画像选择、代码风险、差异比较和导入 URL 中使用版本 ID。

## 4 目标业务规则

### 4.1 单例范围

业务唯一键是 `(requirement_id, generation_kind, stage)`，不是“某个 task 的 stage”。同一需求的 function、api、ui 等生成类型分别有唯一当前链。

重新配置现有需求链更新该链的配置，不创建另一套可以同时成为当前内容的任务。旧的多个配置任务作为执行来源留在历史中，不再通过“最近一条任务”动态决定当前业务结果。需求无关独立任务及其他辅助任务不套用这个唯一键。

### 4.2 当前内容与候选

- 每阶段最多一份当前确认内容，没有采用过时为空。
- 每阶段可有多个候选。首期仍最多一个活动生成；已有待审候选不再阻止下一次生成，多候选不等于必须并行生成。
- 每次重新生成追加候选，不自动替换当前内容。优化默认派生新候选并记录 derivedFromCandidateId，原候选保持。
- 未采用且未被下游引用的候选可人工编辑，使用自身令牌和 expectedAttemptId 防并发覆盖。当前、曾采用或已被下游引用的候选快照保持不可变，修改须派生新候选。
- 候选可比较、试生成下游、确认采用、拒绝或丢弃；未采用候选只能作为显式试生成输入，不能作为默认正式输入或导入源。
- 确认采用原子替换唯一当前正文和来源信息；原采用候选及其他候选保留。再次采用旧候选必须重新检查当前来源，不能绕过失效规则。
- 拒绝/丢弃只作用于指定候选，不清理同阶段其他候选。失败运行不产生可采用的空候选，也不清空当前内容。
- 当前采用标记只由唯一当前内容的 source_candidate_id 派生，不能给多个候选独立设置有效标签。
- 当前采用候选不能直接删除；须先换选其他候选，不自动恢复上一个候选。

重新生成默认只读取当前有效上游。用户选择“基于候选试生成”时，每个必需上游阶段只选择一个来源，允许候选与当前结果组合，但整条来源不得冲突。模型只得到所选内容及必要依据，不会读取整个候选池。优化沿用被选候选的冻结来源；候选比较默认是界面差异查看，不自动发起模型比较。

### 4.3 当前可见不等于可继续使用

当前采用链与既有下游来源不匹配时，下游当前内容可以保留查看，但标为“待更新”，不再用于默认生成、正式导入或将来的默认知识检索。候选是否还能试生成要另查来源完整性：仅未被采用或与当前选中分支不同，可以继续试生成；原文/接口等实际依据变化、源候选被拒绝或丢弃、快照缺失等情况则不能继续使用。

候选的冻结来源后来逐级被采用且完全一致时，可以直接核验并采用该候选，不强制重新调用模型。不能只点“设为有效”跳过核验，也不能把不一致来源改写成当前来源后宣称一致。

审核并替换内容不自动修改已经导入的正式用例。用户仍需执行导入预览/确认，且没有新的用例内容时不触发正式资产变化。

### 4.4 运行历史的用途

历史运行可查看允许保留的输入、输出及审核/导入记录，但没有按历史运行直接导入或作为上游的入口。候选池负责比较和明确的试生成选择，运行历史负责审计。默认生成读取当前有效输入；同请求重放只返回原结果，不重新激活旧内容。

旧尝试通过保留策略清理。当前正文与导入回执必须自包含，不能因清理某条来源 attempt 就消失。外部文件引用仍遵守现有文件引用与清理规则。

## 5 目标数据模型

### 5.1 唯一当前链

拟新增 `requirement_generation_chains`，至少包含 chain_id、requirement_id、kind、task_id、created_at，数据库唯一约束为 `(requirement_id, kind)`，并保证绑定 task 属于该需求和类型。

该表只负责确定当前任务容器，不保存业务内容版本。需求链配置读取和创建经统一入口，原 `newConfiguration` 在四类需求链范围内退出；需要重置时更新当前链配置并按实际输入变化标记产物，不偷偷创建第二条链。

### 5.2 多候选池

拟新增 `ai_generation_candidates`：candidate_id、chain_id、stage_id、origin_attempt_id、current_attempt_id、derived_from_candidate_id、正文/格式/来源快照、candidate_token、处置状态、来源新鲜度及创建者/时间。

候选与 attempt 分离：每次重新生成或优化派生形成新候选；尚未被采用且未被下游引用的候选可人工保存编辑 attempt，并更新正文和 token。一旦被下游试生成冻结引用，该候选快照即不可变，后续编辑或优化必须派生新候选。失败只留运行记录。候选自己保存必要内容和来源，不依赖可被清理的执行记录才能读取。

处置状态为 available/rejected/discarded；available 不代表已审核或当前生效。是否被采纳通过审核事件记录，isCurrent 只从当前内容来源指针派生。来源完整性 sourceIntegrity 为 valid/stale/source_unknown；采用对齐 adoptionAlignment 为 aligned/pending_upstream/mismatch。两者分别表达“能否按冻结依据继续试生成”和“是否具备正式采用条件”，不能合成一个 stale 状态。

采用 B 不会自动拒绝 A/C，也不会仅因换选而破坏 A 分支的冻结来源。当前/曾采用/已被下游引用的候选不能就地改写；拒绝候选若需修改，派生新候选。拒绝或丢弃会阻止新的引用和采用，其下游依赖显示来源不可用；不能因为保留了快照就绕过来源处置。

候选及尝试增加 generationMode（current/trial）、source_manifest_json、lineage_hash、来源快照固定标识和派生关系。manifest 记录每条实际依赖的需求、链类型、阶段、来源类别、candidateId（如有）、snapshotId、contentHash、basisHash、输入批次与祖先引用。lineage_hash 来自确定性规范化的完整来源闭包，服务端计算，不能使用客户端声称一致的值。

generationMode 记录产生方式，采用后也不改写 trial 为 current。采用资格通过来源闭包和当前选择重新计算；试生成不等于永久不可采用。

### 5.3 每阶段当前内容

拟新增 `ai_generation_stage_contents`，每个当前链阶段至多一行。`stage_id` 唯一，另以 chain_id + stage 建唯一约束，防止任务绑定错误形成两份当前内容。

| 字段 | 含义 |
| --- | --- |
| stage_id、chain_id、stage | 稳定阶段及当前链身份 |
| content、format、context_json | 唯一当前确认正文、格式和必要上下文 |
| content_hash | 规范化正文的哈希，用于判断实际内容变化 |
| basis_hash | 本次确认所依据的实际输入指纹，不包含时间戳和临时 URL |
| content_token | 不透明并发令牌，每次有效确认/清空改变；不是可查询历史版本的 ID |
| source_manifest_json | 依赖的稳定来源身份、内容/依据哈希、选择范围和批次 |
| lineage_hash | 确认时核验通过的整条来源闭包指纹，导入时再次核对 |
| source_snapshot_json | 当时实际输入副本及必要来源上下文；支持运行记录清理后继续解释当前内容 |
| source_attempt_id | 来源尝试审计引用，可空；删除 attempt 不级联删除当前正文 |
| source_candidate_id | 当前采用候选；所有候选的当前标记从该指针派生 |
| confirmed_by、confirmed_at、comment | 当前确认信息 |
| invalidated_at、invalidated_reason | 待更新原因；结合来源实时核验，不单独信任缓存状态 |

清空可删除正文行，但需在稳定 stage 上保留新的 mutation token，或保留正文为空的单例行作为 tombstone；建议保留单例行及 token，防止删除再创建时旧客户端请求意外命中。

查询列表只读摘要、状态和令牌；正文与源快照通过详情读取，避免新增大字段导致列表加载全部内容。

### 5.4 审核和执行记录

尝试继续保存输入输出、operation、状态、错误和失效信息。需求链尝试也记录 reviewer、reviewed_at、review_status，不再以“存在版本行”判断是否审核过。

拟新增或复用统一请求回执机制记录审核事件：request_id、请求指纹、attempt_id、审核结论、结果 content_token、操作者，以及 continue_after 的后续请求身份。它用于审计和幂等，不保存可选择的完整业务版本库。

当前内容已被之后操作替换时，重放旧的审核请求只返回“当时审核已成功”的回执，不能把旧内容重新写回当前行。

### 5.5 导入回执

将 `ai_generate_version_imports` 演进并重命名为 `ai_generate_imports`，保留 import_id 和正式目标指针，去掉 version_id 外键及 parent_versions_json 依赖。

回执保存 source_kind（当前阶段或独立候选）、稳定阶段/任务身份、source_content_token、content_hash、basis_hash、审核信息、实际导入内容/来源快照、目标、changed_case_ids 和导入操作者。source_attempt_id 是审计定位，不作为回执存活前提。

同一次请求重放和重复导入通过 request_id、源 token、目标/选择指纹及数据库约束控制。具体幂等粒度在实现时覆盖多目标导入，不能仅用一个全局内容哈希阻止合法的不同目标导入。

独立候选导入继续使用其 attempt 审核机制，适配新的回执结构；本轮不改独立任务的业务生命周期。删除任务/运行后的回执保留或最小化策略需统一实现，不得让旧的 CASCADE 意外删掉当前来源说明。

### 5.6 候选身份与技术标识的区别

候选按 candidateId 查看、比较和确认。content_token、attemptId、sourceBatchId 不构成另一套正式版本选择；旧 token 不能用于读取旧正式内容或导入，只用于防止确认、编辑和导入时的并发覆盖。

即使 A → B → A 正文恢复相同，token 也改变，旧编辑请求不能覆盖新状态。来源一致性核对冻结来源身份、正文、依据和有效性；同一快照重复确认等纯元信息变化不要求重跑，换成另一个候选则不能仅凭正文相同认定一致。

## 6 当前内容状态与操作矩阵

不要再用单个 stage.state 同时代替“当前内容是否有效”“是否有候选”和“是否正在运行”。响应应分开表达：

- currentState：empty / valid / stale / source_unknown。
- candidates：分页候选列表和数量，每个候选有处置状态、新鲜度及防冲突令牌。
- executionState：idle / running / failed。
- importState：not_imported / imported / changed_since_import。

| 场景 | 当前内容 | 候选 | 行为 |
| --- | --- | --- | --- |
| 从未生成 | 空 | 无 | 默认生成需要当前上游；显式试生成可选择有效上游候选 |
| 正在重新生成 | 原内容保持 | 原候选池保持，等待新候选 | 原内容有效时可使用；首期只禁止同阶段并行生成 |
| 生成成功 | 原内容保持 | 追加待审候选 | 可比较或显式试生成下游，不能直接导入 |
| 生成失败 | 原内容保持 | 无新有效候选 | 展示本次失败，不把旧内容标成失败产物 |
| 拒绝指定候选 | 原内容保持 | 仅该候选被拒绝 | 其他候选保持，不自动回退 |
| 确认采用指定候选 | 替换为该内容 | 保留池并切换当前标记 | 同事务记录采纳，按实际变化传播失效 |
| 仅切换上游采用项 | 不匹配的下游 current 待更新 | 冻结来源完整的分支仍可试生成，采用对齐变 mismatch | 最终采用仍要求逐级对齐 |
| 真实根输入变化或来源被拒绝/丢弃 | 相关 current 待更新 | 对应来源 stale/不可用 | 不允许借试生成绕过实际失效 |
| 运行中只切换当前采用项 | 原内容按依赖判断 | 来源完整时可保留试生成候选，标明未对齐 | 不自动采用或改写输入 |
| 运行中真实依据失效 | 原内容按依赖判断 | 结果仅作过期诊断 | 不可继续试生成、采用或导入 |

如果当前内容已 stale，重新生成候选失败后仍保持 stale，不因为“还有旧正文”而恢复有效。

## 7 上下游依赖与失效传播

### 7.1 沿真实消费关系传播

现有阶段定义以 [domain/generation_chain.py](../../apps/control-plane/src/testing_agent/domain/generation_chain.py) 为准：

```text
需求原文 ─→ requirement_review  提示报告
需求原文 ─→ extracting_text
                 └─→ function.requirement_analysis
                         └─→ case_names
                         └────────┬─→ detailed_cases
                                  └─ 同时依赖 case_names

选中接口定义 ─→ interface_extract ─→ api_design
                       └──────────────┬─→ generate
                                      └─ 同时依赖 api_design

源码 pin + 正式功能用例 ─→ ui_surface ─→ ui_design
                              └──────────┬─→ ui_yaml
                                         └─ 同时依赖 ui_design
```

需求评审不成为材料整理的前置。不能因为前端画布连了一条线，就增加材料→API 或画像正文→UI 的事实依赖。API 的实际需求上下文如果被本次输入消费，才登记对应指纹；仅作为展示的引用不扩展失效面。

### 7.2 依赖清单

每次运行冻结直接来源和祖先来源闭包。来源至少包含 resourceKind、稳定 identity、sourceKind（current/candidate/business_input/repository_pin）、candidateId（候选源）、不可变 snapshotId、contentHash、basisHash、使用范围及输入批次。来源类别记录当时如何选择，后续采用上游不能改写原始记录。

同时处理三类来源：

1. 阶段产物：当前确认结果，或试生成显式指定的材料、分析、测试点、接口提取和设计候选。每个实际必需阶段只取一份。
2. 本地业务输入：需求正文与附件、选中接口实际定义、所选正式功能用例及相关配置。
3. 外部冻结输入：仓库、分支、具体 commit、运行批次。commit 是运行身份；不为了去业务版本删除 Git pin。

只哈希直接上游正文不够。分析正文相同但材料来源不同，仍可能是两个不同分支。应从冻结 manifest 遍历完整依赖图，并以 `(requirementId, chainKind, stage)` 规范化节点；同一节点在两条路径上出现不同快照，判为来源冲突。来源图必须无环，项目、需求及允许的跨链关系必须匹配，不能伪造非声明依赖。

闭包规范化排除请求时间、选择方式 current/candidate、审核时间、并发 token 和 generationMode 等操作元信息，保留实际候选/来源快照身份、正文/依据哈希、根输入和批次。因此“候选被采用”本身不会改变它的语义来源指纹，也不会导致所有试生成后代必须重跑。原选择方式仍在审计 manifest 中保留。

### 7.3 何时失效

- 开始重跑上游、产生新候选：不会改变当前内容，不主动使下游失效。
- 仅切换或清空上游当前采用项：不匹配的下游 current 待更新；完整可用的候选分支仍可试生成，但 adoptionAlignment 为 mismatch 或 pending_upstream。
- 拒绝/丢弃某候选：不影响无关候选，但依赖该源的试生成分支不能继续引用或正式采用；保留原快照供审计。
- 当前需求原文、附件或选中接口发生实际变化：对应根阶段及后续消费链待更新；新材料/提取审核后按新依据继续。
- 同一内容只改变排版或审核备注：按确定的规范化规则判断是否语义输入不变，避免无意义失效。
- 正式功能用例变化：仅影响实际引用它的 UI 输入；生成链最终候选变化本身不改变正式资产。
- 外部仓库分支前进：保留现有显式 source-check/refresh 机制，不在每次详情读取访问 GitLab。新批次按明确选择的 pin 运行，不能悄悄跟随 HEAD。

所有启动、采用、审核继续、图谱生成和导入入口都重新验证闭包。试生成检查 sourceIntegrity；正式采用和导入还必须检查 adoptionAlignment。持久化状态用于解释和查询，不作为唯一正确性保障。

### 7.4 两个例子

若需求原文或其他实际业务依据改变，旧材料 M 分支不能靠正文相同保持有效；必须重做或重新整理来源并形成新候选。

若根输入未变，用户仅从材料候选 A 改为采用 B，基于 A 的分析/测试点候选仍可保留并继续明确的试生成。它们不能被当作基于 B 的正式结果。将来按顺序采用完全匹配的 A 及其分析后，下游候选经核验可直接采用，无需机械重跑。

### 7.5 试生成启动的整条来源校验

1. 为每个必需的直接上游明确选择 current 或 candidate，禁止一个阶段选择多份。界面可从已选候选的祖先推导其配套上游，但必须展示并在请求中明确提交，服务端重新解析校验。
2. 候选必须已完成、可读取、未拒绝/丢弃、来源完整；它及祖先可以尚未被采用。未完成运行、缺失快照、已失效根输入不能试生成。
3. 遍历每个所选来源的冻结祖先，核验内容、依赖、权限、根输入和批次，形成闭包。复用重复祖先即可，不重复拼入 prompt。
4. 同一必需节点出现不同 candidate snapshot 时拒绝。例如完整用例选择分析 A，但测试点来自分析 B，即使正文相似也不能混用。
5. UI 的 surface/design/yaml 必须沿同一冻结输入批次；API 的提取与设计必须来自同一接口定义快照。不能用跨批次拼接模拟候选试验。
6. 校验通过后只冻结这组所选内容及必要依据，并标为 trial。没有“任何失败都回退到最新当前内容”的行为。

试生成中的候选材料是暂定输入，不是已审核事实。Worker/技能仍需校验内部依据和 Schema，但应识别 trial 来源等级；输出仅进入候选池。当前事实读取、正式资产导入和知识检索不能把这条试验路径当作免审核入口。

### 7.6 最终采用时的完整来源一致性

首版按依赖拓扑逐级采用，不增加“一键把整条上游自动批准”的动作。采用测试点前，其分析及材料必须先被明确采用；采用完整用例前，相关分析和测试点均须已采用且来源一致。

每次采用由服务端执行：

1. 确认待采用候选及冻结快照可用，来源闭包无缺口、环或相互冲突，根业务输入和授权仍有效。
2. 对闭包中的每个必需阶段，读取该阶段唯一 current，要求 current 有效；没有 current 返回 pending_upstream，不代用户采用。
3. 对原来以 candidate 选入的来源，要求 current 对应同一 candidateId、同一不可变候选快照及相同 contentHash/basisHash。仅正文相同、标题相同、曾审核过或同属一个候选池都不足够。
4. 对原来以 current 选入的来源，核对冻结的实际采用候选/来源快照、内容和依据。操作 token 用于防并发，不要求它等于试生成时还不存在的采用 token。
5. 所有祖先需一致，不能只核对直接父节点。API/UI 同时核对接口、commit、正式功能用例及输入批次等真正消费的根输入。
6. 在同一事务中重新核对这些前提，再替换唯一当前内容，记录本次采用的完整来源指纹。输出不一致节点列表及阻塞原因，不把失败结果降级成警告继续采用。

材料 A 被采用后，基于它试生成的分析 A1、测试点 A2 可依次核验采用，不需要重新生成。若采用的是另一份候选 B，即使文字碰巧一样，也不能静默改挂 A1/A2 的来源；首版要求选择原分支或重新生成，不提供隐式来源重绑定。

采用预检可列出待采用/不匹配的上游和建议操作顺序，但不具有审核权限。正式导入再次核验最终 current 的完整来源闭包，防止采用后、导入前发生上游变化。

## 8 派发 审核与并发

### 8.1 启动

1. 解析唯一当前链，校验权限和阶段。
2. 解析 generationMode：current 默认读取当前有效上游；trial 按明确的 sourceSelections 读取候选/当前组合。两者均校验来源闭包，trial 不要求上游先采用。
3. 在外部访问之外准备输入；仓库 HEAD 等远端访问不放在持锁事务内。
4. 短事务重验权限、候选快照和来源状态，冻结实际内容、直接/祖先 manifest、lineageHash、generationMode 和 inputBatch。请求指纹包含模式及完整选择，相同 requestId 不能换源。
5. 创建 attempt 与队列，提交后 Worker 领取。

不再接受旧 upstreamVersions。新试生成使用显式 sourceSelections，只有 trial 模式允许候选来源；current 模式携带候选选择应拒绝，不能悄悄改变语义。浏览器的 expected tokens 只作并发前提，服务端解析真实内容和闭包。

“试生成下一阶段”可以连续执行：材料 A → 分析 A1 → 测试点 A2 → 完整用例 A3 均可先作为候选存在。每次都是有明确输入的单阶段请求，不自动采用任何上游，也不跳过已有阶段的输出契约校验。默认生成在当前上游缺失时不会自动改成 trial。

### 8.2 编辑和继续优化

既未被采用、也未被下游引用的候选编辑携带 candidateId、expectedCandidateToken 和 expectedAttemptId。对当前、曾采用或被下游引用的候选修改必须派生；候选被锁定引用与编辑采用相同并发保护，不能在校验后被原地改写。stage.current_attempt_id 单指针不再代表候选池。

指定候选优化派生新候选并沿用冻结来源。只是未采用或不与当前选择对齐时，可在 trial 模式继续优化；sourceIntegrity 已失效时拒绝沿旧依据优化。不能静默混入新上游，派生失败不影响原候选。

### 8.3 确认替换

```text
核对请求重放和权限
  → 锁定当前链及必要来源/目标
  → 核对 candidateId、expectedCandidateToken、expectedAttemptId、expectedCurrentToken
  → 按 7.6 校验每个祖先均已采用且与冻结来源一致
  → 校验候选产物
  → 覆盖唯一当前内容行，写审核记录
  → 将受影响下游标为待更新
  → 更新唯一 source_candidate_id，保留其他候选
  → 提交
```

重复审核只返回原回执。旧审核成功后当前内容已经再次变化，不能靠重放把旧内容重新发布。

expectedCurrentToken 以用户本次确认采用时看到的当前结果为准，不自动使用候选生成时的旧 token。两个用户同时采用不同候选，只有一个能匹配原 token 成功；另一个刷新并重新比较。某个候选正在生成时，不应仅因阶段 busy 阻止查看、拒绝或采用其他已完成候选；动作仍须通过对应候选及当前内容的并发检查。

### 8.4 审核通过并继续

保留“本阶段确认成功、下一阶段启动失败”的现有两段结果语义。第一次事务确认当前内容并记录 continuation 请求；第二次启动只允许使用刚确认且仍为当前有效的输入。

两段之间若当前内容被别人替换，返回 continuationError，保持本次确认的审计事实，但不偷偷改用新内容继续。用户以新的请求从当前链启动。

“不采用，试生成下一阶段”是独立操作：只创建下游 trial 请求，不复用 approve/continue 的授权效果。前端必须分别显示这两个动作，不能让试生成按钮顺便采用上游。

### 8.5 锁与在途任务

现有 Worker 回传协议要求先锁 WorkerTask，再锁 stage/attempt。新实现必须保留这一顺序，不能在审核持有阶段锁时反向等待队列行造成死锁。

建议采用当前链/阶段上的短事务写屏障，统一派发、确认、导入与来源变更的序列化规则；需要跨当前链检查时按稳定链 ID 排序。Worker 回传先获得其队列锁，再进入同一写屏障；审核和失效传播只处理业务状态/尝试，不同步等待队列取消。已有涉及队列的刷新入口需一并对齐，不能只在新模块中规定顺序。

若根输入写入涉及项目/迭代/需求锁，按现有顺序先取这些父锁，再进入当前链；Worker 已持队列锁后不得追加与其他入口形成逆序的父锁。实现步骤中必须绘制实际锁序矩阵，以 MySQL 并发测试验证，而不是用进程内锁替代。

默认不新增 AI Worker 强制中断协议。在途期间仅改变当前采用项，若原冻结源仍完整，结果可以进入候选池但标明尚未对齐，允许明确试生成；真实源被清除、拒绝、丢弃或根依据改变时，结果仅作过期诊断。执行成功与能否正式采用分别记录，不伪造 Worker 已停止。

UI 多条试生成分支各自冻结 sourceBatchId。现有单个 stage.source_batch_id 和 detach_old_ui_batch 不得无差别作废其他完整候选分支；刷新指定分支只处理该分支在途任务。当前结果的默认批次与候选分支批次分开，跨分支 surface/design 拼接仍拒绝；本轮不扩展为同阶段并行生成。

## 9 导入正式资产

新导入入口按“当前链的最终阶段”定位，不接受历史 version_id 或历史 attempt_id 作为需求链导入源。

预览读取当前有效正文并校验完整祖先来源，返回 source token、内容/依据/lineage 哈希、依赖闭包状态、目标及目标冲突指纹。确认请求携带前提和 requestId；叶子源、任一必需祖先或目标变化导致不一致时，拒绝旧预览。

执行事务重新校验权限、当前源、完整采用闭包及目标，调用现有功能/API/UI 导入器，在同一事务写正式资产和自包含回执。允许复用已有冲突处理，但必须去掉“为了取得正文必须再读取来源 attempt”的前提。不能因为叶子已采用就跳过其祖先状态，trial 标记也不构成独立导入入口。

| 场景 | 行为 |
| --- | --- |
| 新候选待审，但原当前内容仍有效 | 可以明确导入原当前内容，预览展示其确认时间；不得误导为导入候选 |
| 当前最终内容 stale | 禁止新导入，先更新对应链路 |
| 审核替换了最终内容 | 旧预览失效，新内容显示未导入或与最近导入不同 |
| 同请求成功但响应丢失 | 重放返回原回执，不重复写资产 |
| 旧导入回执对应正文已被替换 | 保留当时来源，不提供再次导入旧源的入口 |
| 正式资产被人工修改 | 不反向改写生成当前内容；再次导入仍需冲突预览 |

“已导入”按具体当前内容及目标判断，不能只判断这个阶段曾经有过任意导入记录。原正式用例身份、归属与执行快照保持不变，不在本轮引入新的用例业务版本库。

## 10 辅助能力如何适配

### 10.1 当前材料消费者

将 `approved_material(requirement_id, version_id)` 改成读取当前有效材料的默认入口；功能链在 trial 模式经专门的来源解析路径读取所选材料候选。代码风险、仓库画像、测试单图谱继续使用当前材料，不因生成链开放试生成就自动扩大它们的输入权限。移除旧材料版本参数及别名的业务选择语义。

新运行冻结 `requirementMaterialSource`，包含稳定阶段身份、sourceKind、候选快照（如有）、contentHash、basisHash、确认或未采用标记及实际正文。默认路径缺当前材料不能默默退回原文；明确 trial 允许未采用但来源完整的材料，历史运行仍读自身冻结输入。

测试单图谱读取每条需求当前材料，不能从候选池挑一份凑齐。代码风险、报告等运行结果保留原历史，不在本轮增加新的结果审核门禁。

### 10.2 功能用例图谱

`stage_storage/relations.py` 的源由 version_id 改为当前完整用例及其来源指纹。图谱运行冻结该份完整用例和它实际使用的材料；结果只在来源仍匹配时作为当前派生图谱展示。

切换完整用例候选使实际内容或依据变化后，旧图谱显示待更新；旧运行仍可查看，不能贴到新用例上。候选比较界面若展示某候选历史图谱，必须标为该候选的审计关联，不作为当前正式图谱。

### 10.3 仓库画像与 UI 源码

画像成功运行目前被投影成版本列表。建议改为“多个画像候选 + 一个当前采用画像”，配套唯一当前画像记录或统一当前结果存储。

- 保留画像运行历史及候选比较。
- 用户明确采用某个成功画像作为后续选择仓库的默认依据；不额外引入内容质量审核门禁，但记录采用操作。
- 新成功画像不自动替换当前画像；失败不清空当前画像。
- UI 源码入口只从当前有效画像列出仓库，不再接受任意 profileVersionId；仍保留仓库选择及 profile/latest commit 模式。
- UI 启动复制实际仓库、分支、commit、功能用例和来源批次，使用本次发起人授权。
- 已冻结 UI 批次不随画像换选自动变更。画像用于选择 pin 的历史身份是审计依据，不能仅因新画像文字变化就改写已冻结源码。
- 新 UI 批次须验证当前画像和实际输入。当前 UI 的状态检查继续关注真正使用的正式功能用例、pin 和批次，不能把画像正文当成 UI 生成事实。

这会调整 ADR 0011 中画像版本选择接口，需同步 source-options/source-check、前端画像面板及源码设置。Git commit 固定能力保持。

### 10.4 独立任务与执行 Worker

DirectStageStorage、尝试查询和导入回执同时被独立任务消费。需求链多候选逻辑应经明确的任务域分支或独立 Module 接入，不能全局改变独立检查点任务的 current_attempt 或审核状态含义。

API/UI 执行 Worker 继续执行正式资产冻结规格，integration-worker 和 perf-worker 不因本轮改变运行语义。AI Worker 继续消费冻结输入并按 attemptId 回传；协议格式版本和本地结果回传 outbox 保留。

## 11 HTTP 与数据契约改造

下表是建议的最终接口形态；具体命名在实现时遵循当前响应信封与字段规范。

| 现有接口或字段 | 目标变化 |
| --- | --- |
| 链详情中的 latestVersion、versions、versionNo | 改为 current 摘要、候选计数/分页入口、独立运行状态 |
| `GET .../versions/{versionId}` | 候选通过 `GET .../stages/{stage}/candidates/{candidateId}`；当前结果通过 `GET .../stages/{stage}/current` |
| `DELETE .../versions/{versionId}` | 指定候选丢弃；当前结果清空另设受 token 保护的动作 |
| `run.upstreamVersions` | 旧字段退出；默认 current 解析当前结果，trial 使用明确 sourceSelections 和冻结来源闭包 |
| `POST .../stages/{stage}/run` | 增加 generationMode=current/trial；成功只追加候选，试生成不采用上游 |
| stage 级 draft/revision 隐含唯一候选 | 请求/路径必须指定 candidateId；编辑带 expectedCandidateToken/expectedAttemptId |
| stage review 只识别 current_attempt_id | 指定 candidateId、expectedCurrentToken，并逐节点校验冻结祖先与各阶段 current 一致 |
| `.../versions/{versionId}/import-options` 与 `/import` | 改为最终阶段 current/import-options 与 current/import；源 token 防漂移 |
| sourceProfileVersionId、画像 versions | 当前画像与画像候选入口；UI 不接收任意旧画像版本 |
| requirementMaterialVersionId 及旧别名 | 删除业务选择；只读来源信息改为当前材料身份与指纹 |
| versioning.upstreamVersions、baseVersionId | 新快照写直接/祖先 sourceManifest、basisHash、lineageHash、候选快照及输入批次 |
| sourceFormatVersion、schemaVersion、workflowVersion | 保留，必要时升级协议值，不做全局字符串删除 |

链概览示例：

```json
{
  "stage": "case_names",
  "current": {
    "sourceCandidateId": "candidate-B",
    "token": "opaque-current-token",
    "state": "valid",
    "contentHash": "sha256:content",
    "basisHash": "sha256:basis",
    "confirmedAt": "2026-11-19T08:00:00Z"
  },
  "candidateCounts": {"total": 3, "trialEligible": 2, "adoptable": 1},
  "execution": {"state": "idle", "activeRunId": null},
  "importState": null
}
```

试生成完整用例的请求示例。界面已明确选择相互配套的分析 A1 和测试点 A2；服务端还要确认 A2 确实来自 A1，且两者祖先一致：

```json
{
  "connectionId": "model-connection",
  "generationMode": "trial",
  "requestId": "f04e7910-6737-4de0-9efb-9beee651a204",
  "sourceSelections": [
    {
      "chainKind": "function",
      "stage": "requirement_analysis",
      "sourceKind": "candidate",
      "candidateId": "analysis-A1",
      "snapshotId": "snapshot-A1",
      "expectedCandidateToken": "token-A1"
    },
    {
      "chainKind": "function",
      "stage": "case_names",
      "sourceKind": "candidate",
      "candidateId": "points-A2",
      "snapshotId": "snapshot-A2",
      "expectedCandidateToken": "token-A2"
    }
  ]
}
```

snapshotId 标识候选实际发布的不可变内容及依据，不依赖可清理的 attempt 行才能读取。sourceKind=current 的选择需携带 expectedCurrentToken；客户端不能直接提供可信正文、父节点图或 lineageHash。服务端返回来源预览，明确自动展开的祖先与试生成等级。

采用请求示例（当前没有结果时 expectedCurrentToken 使用服务端返回的空槽令牌，不用空字符串猜测）：

```json
{
  "action": "adopt",
  "candidateId": "candidate-C",
  "expectedCandidateToken": "opaque-candidate-token",
  "expectedAttemptId": "attempt-C",
  "expectedCurrentToken": "opaque-current-token",
  "requestId": "40b5b45c-c03d-4e2a-9957-8e76f7db3f46",
  "continueAfter": false,
  "comment": "当前范围覆盖更完整"
}
```

候选列表只返回摘要、生成来源、有效性和采用标记，正文单独读取。比较由用户选择两个候选或候选与当前内容；比较本身不自动发起模型请求，也不把整个候选池送给生成模型。

拟新增采用预检响应 `adoptionCheck`，返回 canAdopt、lineageHash、blockingSources 和待采用顺序。阻塞原因至少区分上游未采用、当前分支不匹配、来源失效/缺失、源快照冲突和并发变更。预检不产生采用效果；实际提交仍需事务内复验，不能凭旧 canAdopt=true 直接写入。

这是破坏性业务契约变更，应成套发布控制面与 Studio。旧版本选择请求不能被静默忽略并改读当前内容；退出期返回明确的功能已迁移错误。历史快照按协议代次只读解析，正常新运行不保留两套可写版本模型。

## 12 Studio 交互

每个阶段页面包含三部分：

1. **当前采用结果**：唯一正文、确认信息、来源和有效/待更新状态。
2. **候选列表**：生成时间、简要说明、基于什么输入、当前/曾采用、待确认、已拒绝或输入过期。
3. **运行记录**：执行中、失败、回传等诊断信息，不与候选列表混成“版本历史”。

主要动作：默认再生成、基于候选试生成下一阶段、比较、编辑可变候选、基于候选优化、确认采用、拒绝/丢弃，以及最终阶段的导入。“确认采用并继续”和“不采用，继续试生成”必须明确分开。

移除旧的任意版本选择控件。默认模式显示当前来源；trial 模式打开按必需阶段分组的来源选择器，每阶段单选候选或当前内容，展示配套祖先和分支冲突。未采用来源不显示成错误，真实失效来源禁用。原“与上一版比较”改成明确选择比较对象。

候选详情展示“生成来源链”和“正式采用阻塞项”：例如材料 A → 分析 A1 → 测试点 A2。用户可按顺序跳转采用缺失上游；系统不替用户批准。来源全部对齐后允许采用现有试生成候选，不强制重跑。切换采用时展示受影响下游，不把采用成功显示为正式用例已更新。

生成新候选期间当前结果和已有候选仍可阅读。一个候选编辑冲突不能让其他候选丢失；拒绝 C 不影响与它无依赖关系的 A/B，依赖 C 的后代须显示来源不可用。候选列表分页，不能在链概览一次性加载全部正文。

代码风险、仓库画像、UI 来源配置同步移除材料版本下拉框。仓库画像展示候选和唯一当前画像；UI 启动只显示当前画像选出的仓库及实际 commit 模式。

样式、主题和组件分层沿用 Studio 现行规范；本方案不另外设计一套页面皮肤。

## 13 影响范围清单

| 区域 | 核心现有路径 | 改动内容 |
| --- | --- | --- |
| 配置与当前链 | `services/requirement_design.py`、`repositories/requirement_design.py`、`repositories/generation_chain.py` | 固定当前链，不再按最近配置任务猜测；处理 new_configuration |
| ORM 与基线 | `models/ai_generation_stage.py`、`models/ai_generation_attempt.py`、`models/ai_generate_stage_version.py`、`models/ai_generate_version_import.py`、`models/__init__.py` | 候选、当前内容、当前链、审核/导入回执；退出旧版本外键/计数 |
| 阶段读写 | `services/stage_storage/__init__.py`、`commands.py`、`upstream.py`、`run_command.py` | current/trial 双路径、候选快照固定、闭包冲突检查、唯一采用 |
| 状态与来源展示 | `stage_storage/views.py`、`chain_view.py`、`version_views.py`、`version_delete.py` | 当前/候选/运行分开，旧版本详情与删除逻辑退出 |
| Worker 事件 | `stage_storage/worker.py`、`worker_events.py`、`payload.py`、`authorization.py`、`ui_batch.py` | 结果追加候选，区分未对齐与真实失效，UI 按分支批次处理，保持租约及锁序 |
| 生成链导入 | `services/generation_chain.py`、`function_generate_import.py`、`api_generate_import.py`、`ui_generate_import.py` | 只导入当前，使用冻结源适配旧导入器；不依赖历史版本/attempt 存活 |
| 独立导入和删除 | `services/standalone_import.py`、`standalone_execution_delete.py`、`repositories/standalone_import.py`、`repositories/deletion.py` | 共用回执模型适配，不改变独立任务审核语义 |
| 历史查询 | `repositories/direct_attempt_history.py`、`direct_attempt_view.py`、`standalone_history.py` | 审核/导入状态不再连接旧版本表推导；候选状态不误计为当前 |
| 材料来源 | `services/requirement_material_source.py`、`functional_requirement_source.py` | 默认当前材料；功能 trial 显式候选材料；冻结来源等级与完整依据 |
| 辅助读取 | `services/code_risk_analysis.py`、`repository_profile.py`、`test_order_graph.py`、`ai_run_launcher.py` | 移除材料版本参数和旧别名，统一当前输入 |
| 派生图谱 | `services/stage_storage/relations.py` | 当前完整用例及来源指纹，候选比较与当前图谱分开 |
| 仓库画像 | `services/repository_profile_versions.py`、`ui_generation_source.py`、`ui_generation_sources.py` | 画像候选与唯一当前画像，UI pin/批次复制保持 |
| HTTP | `schemas/generation_chain.py`、`schemas/ai_generate_task.py`、`routers/requirements.py`、`routers/repository_profile_tasks.py`、相应 handlers | 候选与 current 契约；旧版本路由与字段退出 |
| AI Worker | `platform/task_source.py`、`platform/schemas.py`、`models/task.py`、相关 tasks 与默认技能 | current/trial 来源等级、暂定依据校验；保留格式版本，仅消费选中输入，不自行采用 |
| Studio 主链 | `features/ai-testing/api/generationChain.api.ts`、`hooks/useRequirementGenerationChain.ts`、`components/GenerationChainModal.tsx`、`GenerationChainImportModal.tsx`、`RequirementGenerationPanorama.tsx` | 候选试生成选择、来源链、逐级采用阻塞、current 导入及全链复验 |
| Studio 辅助 | `useRequirementCodeRiskWorkspace.tsx`、`useRequirementRepositoryProfileWorkspace.ts`、`useUiGenerationSourceSelection.ts`、`RequirementRepositoryProfileInspector.tsx`、`UiGenerationInputsModal.tsx`、`UiGenerationSourceConfig.tsx` | 移除任意历史版本选择；画像候选采用、当前源码来源 |

控制面路径相对 `apps/control-plane/src/testing_agent/`；AI Worker 相对 `apps/ai-worker/src/testing_agent_ai_worker/`；Studio 主链相对 `apps/studio/src/`，辅助文件位于同 feature 的 hooks/components。实际实施以入口依赖检索继续补齐，不用全局替换 version 字符串处理协议版本。

## 14 旧数据转换方案

> 2026-11-20 用户补充：旧生成版本、候选和运行历史不需要迁移，已有正式功能、API 和 UI 测试用例必须保留；本轮不连接或修改业务数据库。以下转换方案作为历史设计参考，不再是本阶段完成条件。

### 14.1 先只读盘点

统计每个需求/类型的配置任务、阶段版本、当前候选、活动 attempt、导入回执和来源缺失。输出稳定映射：旧 task/stage/version/attempt → 当前链/candidate/current，并列出异常。

不在本轮连接或修改业务数据库。不能把代码中允许多个配置任务等同于真实库中已经存在重复。

### 14.2 默认转换规则

| 旧数据 | 处理 |
| --- | --- |
| 当前链容器 | 默认采用与现有链入口相同的任务；若多配置存在业务歧义，盘点报告列出并确定映射，不能跨任务随意拼阶段 |
| 已审核阶段版本 | 转为保留的候选，原审核信息作为历史采纳证据；不自动视所有候选为当前有效 |
| 当前阶段结果 | 默认以现有入口显示的 latest 已审核内容初始化唯一 current；没有则为空，不能自动采用草稿 |
| 待审核当前草稿 | 转为待确认候选；其他有正文且允许保留的尝试按明确资格转换或只作历史，避免所有中间输出都变成候选 |
| 上游来源匹配 | 从确切旧版本映射核对实际内容/依据，构建 manifest；不按时间猜测 |
| 仅与当前采用分支不一致 | current 标待更新；候选若冻结来源完整且根输入有效，则 sourceIntegrity=valid、adoptionAlignment=mismatch，可试生成但不可直接采用/导入 |
| 真实来源已改变、被拒绝/丢弃或批次冲突 | 候选来源标 stale/不可用，不允许继续试生成；快照留作审计 |
| 来源缺失或无法核对 | source_unknown，给出需重做范围；不伪造哈希和审核 |
| 导入记录 | 先复制当时实际正文、审核及目标证据，保留 import_id；缺失内容记明缺失，不伪造来源 |
| 画像版本 | 成功结果转为画像候选，按原默认入口确定初始当前画像；UI 已冻结 pin 保持 |
| 已运行 UI 批次与正式执行 | 原输入、commit 和快照不改写成新当前内容 |
| 正式资产 | 保持 ID、内容、归属和执行证据，不因本次迁移重新导入 |

不承诺所有迁移产物都立即可采用。旧来源能映射为完整候选分支时可继续试生成；来源冲突或缺失则明确阻塞。不自动批准祖先，也不偷偷改选更旧材料让 current 状态变绿。

### 14.3 转换与切换顺序

1. 编写并验证只读盘点和可重入转换工具，保留备份与恢复演练结果。
2. 在明确维护窗口停止相关新派发、编辑、审核和导入，排空或按现有协议结束在途 AI 任务；处理 Worker 回传 outbox 和租约，避免旧结果迟到写入。
3. 转换候选、当前链、当前内容、审核事件及导入快照，记录检查点和旧新 ID 映射。
4. 对账正文哈希、候选/当前数量、归属、导入目标、正式用例总量及来源有效性。
5. 成套切换控制面、Studio 和需要适配的 AI Worker；新版仅写新模型，旧版本选择端点明确退出。
6. 验证后开放写入。候选/current 数量和正式资产对账不符时不得继续。
7. 清理旧版本外键、旧读取代码和表；保留离线备份到约定回退期限，不让备份成为在线第二套业务版本入口。

仓库处于预发布单基线阶段：模型及最终结构只修改 `20261103_0001_v1_baseline.py`，不新增 update migration。已有数据库必须通过受控转换工具或新结构库导入处理，不能靠 `alembic upgrade head`/`stamp` 假装完成已有表改造。可丢弃开发库另可重建，但不得默认销毁现有数据。

### 14.4 回退

写入开放前可按验证过的备份整体恢复旧应用和旧数据。新模型开始接受候选/采用/导入后，不能只切回旧二进制；必须先暂停写入并评估新数据映射，或采用向前修复。迁移新结构后不承诺无损随时回滚。

## 15 实现步骤与先后关系

下面是改造实施顺序，不代表已开始开发。

| 步骤 | 实现内容 | 依赖 | 验收出口 |
| --- | --- | --- | --- |
| 1 固定领域与契约 | current/trial、多个候选、唯一采用、来源完整性/采用对齐、逐级确认；记录 ADR | 本方案评审 | 试生成不等于采用，整条来源校验规则明确 |
| 2 盘点旧数据与测试样例 | 多配置、来源不一致、导入、画像及候选样本；只读转换映射 | 1 | 无正文丢失的转换规则与异常清单 |
| 3 新存储模型 | 候选不可变引用、直接/祖先 manifest、lineageHash、current 及回执；唯一 baseline | 1、2 | 来源可遍历，已引用快照不被改写，当前唯一 |
| 4 来源解析与闭包模块 | current/trial 双路径、祖先展开、分支冲突、根输入有效性与采用对齐 | 3 | 不混来源、不把未采用误判失效、不凭正文相同通过 |
| 5 多候选生成与采纳 | 指定候选试生成、采用预检、拓扑逐级确认、事务复验、CAS 与审核继续 | 3、4 | 完整分支可先试生成再逐级采用，无需机械重跑 |
| 6 Worker 与批次适配 | trial 来源等级、回传对齐状态、UI 分支批次与旧契约 | 4、5 | 切换 current 不毁试验分支，真实失效不能被采用 |
| 7 当前内容导入 | 源/闭包/目标预览与事务复验、自包含回执；独立导入适配 | 3、5 | 祖先变化也拒绝旧预览，重放不重复写 |
| 8 辅助入口 | 代码风险/画像/测试单图谱、功能图谱、画像候选及当前画像 | 4、6 | 无隐藏的旧版本上游入口，UI pin 不漂移 |
| 9 Studio 改造 | 模式与来源选择、候选比较、来源链/阻塞、逐级采用、导入及辅助入口 | 5、7、8 的契约稳定 | 可完成 A/B 分支试验→选择→逐级采用→导入 |
| 10 旧契约退出 | 新建配置默认进入候选模式，移除旧版本选择、读取及表结构 | 2–9 | 新结构下正常流程通过，已有正式测试用例保持独立 |
| 11 联调验收 | 真实 MySQL 并发、跨端与模型烟测；本轮不操作业务库 | 10 | 如实记录通过、跳过及未验收项目 |

候选/当前规则集中到 StageContent Module，Interface 包括 `list_candidates`、`prepare_candidate(mode, selections)`、`check_adoption`、`adopt_candidate`、`read_current`、`clear_current`。内部共用来源闭包解析与完整性/采用对齐校验，处理唯一性、CAS 和审核幂等；导入复用同一校验实现，不能各写一套“来源一致”。具体 HTTP 和队列适配留在现有层次中。

## 16 验收场景

| 场景 | 必须满足的结果 |
| --- | --- |
| 连续生成 A/B/C | 三个候选可查，已有待审候选不阻止下次生成；未采用前 current 不变 |
| 采用 B | 仅 B 是当前，A/C 不被删除、不进入默认输入；仍可明确选择完整候选试生成 |
| 再生成 D 失败 | 当前 B 与原候选保持 |
| 拒绝 C | 不清空 A/B/D，不修改当前结果 |
| 编辑或优化已采用 B | 创建新候选，B/current 保持到新候选被采用 |
| 同时采用 A 和 C | 同一 expectedCurrentToken 最多一个成功，另一个明确冲突 |
| 重放旧采用请求 | 返回旧操作回执，不重新激活旧当前 |
| 仅切换上游当前采用 | 不匹配 current 待更新，完整候选分支仍可试生成；正式采用需重新对齐 |
| 上游只生成候选未采用 | 下游继续使用原当前，不提前作废 |
| 已失效上游正文与以前一样 | 仍检查依据与有效性，不只比正文哈希 |
| 下游运行中当前分支切换 | 冻结输入不改，来源完整则保留未对齐候选，不自动采用 |
| 下游运行中真实根输入变化 | 结果标真实失效，只可审计，不继续试生成或采用 |
| 审核继续两段之间发生替换 | 返回 continuationError，不用新内容偷偷继续 |
| 采用候选未导入 | 正式用例没有变化 |
| 导入前源/目标变化 | 旧预览被拒，不导入错内容 |
| 删除历史运行 | 正式资产及过去执行快照保持；候选删除规则准确 |
| 多配置任务旧数据 | 只生成一个当前链，不让每任务各有一份生效内容 |
| 来源缺失或分支不一致 | 区分 source_unknown 与 adoptionAlignment mismatch，不按时间推断有效 |
| 画像切换和 UI 历史批次 | 新运行读取当前画像，已有运行的 pin/用例不改 |
| 无需求独立任务 | 审核、导入、删除、结果回传仍正常 |
| 跨项目/只读/开发角色 | 候选、current、快照、采用和导入权限一致 |
| 上游尚无 current，存在有效候选 A | 默认生成阻塞；显式 trial 可以生成 A1，不能自动采用 A |
| A→A1→A2 连续试生成 | 每次只冻结一套明确来源，所有输出留在候选池，不更新 current |
| 完整用例选分析 A1、测试点来自 B1 | 启动前发现祖先冲突并拒绝，不靠标题或正文相似放行 |
| 采用 A2，但 A/A1 尚未采用 | 返回具体缺失上游及顺序，不自动批准、不部分改 current |
| A 与 A1 逐级采用且快照完全匹配 | A2 核验后可直接采用，不要求重新生成、不改写 trial 出身 |
| 采用另一个正文相同的材料 B | A 分支后代仍不能静默改挂，候选身份及 basis 必须一致 |
| 上游候选已被试生成引用后编辑 | 必须派生新候选，旧后代快照和来源图不变 |
| 上游候选被拒绝或丢弃 | 无关候选不受影响，依赖该源的试生成/采用被阻止 |
| 试生成引用缺失、无权限或构造来源环 | 服务端拒绝，不回退最新 current、不信任客户端图 |
| 试生成期间仅采用了它实际使用的祖先 | 来源指纹保持，结果可按对齐情况采用，不误判为过期 |
| UI 候选跨批次或 API 提取/设计来源冲突 | 启动和采用均拒绝；刷新一条分支不无差别清理另一完整分支 |
| 叶子已采用，导入前祖先改选 | 导入完整闭包复验失败，即使叶子 token 没变也不写资产 |
| trial/current 或候选选择变化后复用 requestId | 请求指纹冲突，不返回另一组输入的运行结果 |

优先更新现有测试：控制面的 `test_direct_stage_storage.py`、`test_direct_stage_storage_mysql.py`、`test_generation_chain.py`、`test_generation_chain_api.py`、`test_stage_request_replay_mysql.py`、`test_requirement_material_source.py`、`test_function_generation_source.py`、`test_function_requirement_versions.py`、`test_ui_generation_repository_source.py`、画像/图谱/独立导入与删除专项。

AI Worker 验证 source format/workflow 协议未误删、current/trial 来源等级、暂定材料依据校验、单阶段产物权限、分批及回传 outbox。Studio 验证默认/试生成选择、来源链与采用阻塞、逐级采用、未保存编辑、冲突、画像和导入；需真实浏览器检查列表和长内容。

具体命令遵循 [验证命令矩阵](../../docs/commands.md)。实施时真实 MySQL 并发与迁移不能用 SQLite 替代；本次只编写方案，不声称这些实现验收已通过。

## 17 设计决策与本轮边界

本稿按最新讨论采用以下设计：默认生成读取当前结果，指定候选允许连续试生成；多个候选、一个当前结果；首期单阶段单活动生成；引用后的候选快照不可变；来源完整性与当前采用对齐分开；最终采用按完整闭包逐级核验；采用与正式导入分离且导入再验全链。

用户已确定当前不设置候选数量上限，也不按保留期自动删除候选，后续根据实际使用情况再制定清理规则。历史运行保留期和旧数据维护窗口仍需另行确定；这些参数不影响上述核心模型，也不要求现在部署任何新基础设施。

本轮不做全局删除 version 字段，也不新增正式用例业务版本库。候选版本可以存在并用于明确试验；唯一性约束作用于当前采用结果，以及单次运行每个必需阶段的一份来源。首版不提供整条分支一键自动批准、来源隐式重绑定或历史执行直接导入。

改造完成后再重估历史知识库：它只取每需求/阶段当前有效内容与正式资产，候选池默认不索引。此前 RAG 计划中业务版本选择、正式用例 revision 和跨需求派生等任务需要重新评估，不能未经复核沿旧依赖直接执行。

## 18 现有依据

- [生成链与阶段规则](../../docs/control-plane/generation-chain.md)
- [当前阶段定义及真实依赖](../../apps/control-plane/src/testing_agent/domain/generation_chain.py)
- [生成配置入口](../../apps/control-plane/src/testing_agent/services/requirement_design.py)
- [链查询及最新版本选择](../../apps/control-plane/src/testing_agent/repositories/generation_chain.py)
- [审核与尝试存储](../../apps/control-plane/src/testing_agent/services/stage_storage/__init__.py)
- [采用并继续](../../apps/control-plane/src/testing_agent/services/generation_adoption_application.py)
- [Worker 回传锁序](../../apps/control-plane/src/testing_agent/services/stage_storage/worker.py)
- [正式导入及来源](../../apps/control-plane/src/testing_agent/services/generation_chain.py)
- 运行历史对版本表的依赖（对应旧代码已删除）
- 画像版本投影（对应旧代码已删除）
- [UI 来源解析](../../apps/control-plane/src/testing_agent/services/ui_generation_source.py)
- [前端链状态与版本选择](../../apps/studio/src/features/ai-testing/hooks/useRequirementGenerationChain.ts)
- [前端生成链接口](../../apps/studio/src/features/ai-testing/api/generationChain.api.ts)
- [ADR 0011 UI 来源](../../docs/control-plane/adr/0011-ui-generation-repository-source.md)
- [ADR 0017 API 先设计后生成](../../docs/control-plane/adr/0017-api-design-before-generation.md)
- [ADR 0018 提示性需求评审](../../docs/control-plane/adr/0018-requirement-review-advisory.md)
- [ADR 0014 预发布单基线](../../docs/control-plane/adr/0014-pre-release-single-baseline.md)

实施前为多候选与唯一当前内容记录新 ADR，明确调整旧版本选择语义；按实际改动更新各项目长期文档。本草稿不直接修改现行 ADR、CONTEXT 或任何业务代码。

