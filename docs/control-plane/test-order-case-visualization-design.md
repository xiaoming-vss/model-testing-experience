# 测试单单用例执行可视化：实施设计

日期：2026-11-14。状态：协议、控制面、Worker、Studio 及批量链路已实现；相关自动化和组件浏览器验证已执行，真实模型与人工语义验收尚待完成。本文记录设计与实际接入；具体检查及未通过范围见 [验收记录](test-order-case-visualization-validation.md)。尚未部署到业务环境。

需求来源：`/home/xiaoming/data/文档/test-agent/需求/测试单用例执行可视化需求.md`。最新补充：首期不提供“图解有误”反馈入口、记录或处理流程。实施规格与工单见 [spec](../../.scratch/test-order-case-visualization/spec.md)。以下源码路径均相对仓库根目录。

## 1. 已核对的实现与差异

| 事实 | 代码证据 | 本次处理 |
| --- | --- | --- |
| 执行正文使用加入时快照，操作与预期已配对 | `models/test_order_entry.py` 的 `snapshot_json`；`services/test_order_entry.py` 的 `add_cases`；`domain/function_case_content.py` 的 `CaseContent`（均在 control-plane 源码目录） | 使用 `preconditions`、`steps[].action/expected`，保留空串及原索引，不从用例库重组正文。 |
| 标题、模块等为当前用例派生值，不在正文快照中 | `TestOrderEntry` 的 `case_title` 等派生字段 | 首期模型输入只提供冻结正文与身份；页面可继续显示当前标题，不把实时标题作为推断事实的依据。 |
| 正式执行数据是用例级状态与原因 | `TestOrderEntry` 模型、`TestOrderEntryUpdateRequest` | 不新增步骤判定。上下文及部分旧注释仍提步骤级结果，以现有模型和本次已确认需求为准；不顺带改写历史 ADR。 |
| AI 辅助任务已有执行、尝试、稳定阶段和队列身份 | `services/auxiliary_execution.py`、`services/stage_storage/dispatch.py`；[ADR 0010](adr/0010-unified-ai-execution.md) | 复用单阶段无审核生命周期，新任务类型单独注册。 |
| 整单图谱按 `order_id + task_type` 查任务，接受调用方提供 `graphInput` | `services/test_order_graph.py` | 不复用整单图谱的业务输入或任务查找方式；新任务按执行条目绑定，正文必须由服务端读取。 |
| 通用辅助任务成功回传只要求输出为字符串 | `services/stage_storage/worker_events.py::apply_auxiliary_completion` | 新图解增加专用校验与发布分支；旧任务行为保持兼容。 |
| 阶段当前产物可被任何成功输出替换 | `services/stage_storage/worker.py`、`DirectStageStorage.publish` | 设置独立有效图解指针，`unsupported` 虽是分析成功但不能覆盖旧有效图解。 |
| 模型授权属于本次运行发起者 | `services/personal_authorization.py`、`stage_storage/authorization.py` | 复用 `execute`、测试单归属检查及本人 LLM 授权；不得借用旧运行发起者授权。 |
| 系统默认技能按任务类型获取，校验下载摘要；技能更新覆盖原版本 | Worker 的 `platform/skills.py`、`skill_names.py`；控制面 `services/builtin_skills.py` | 新技能走相同发布方式；记录实际使用的技能内容摘要，不能只存技能名称称作版本。 |
| 工作台文字内容与用例级判定可独立替换 | Studio 的 `TestOrderWorkspacePage.tsx`、`TestOrderCaseContent.tsx`、`useTestOrderWindow.ts` | 在执行内容区接入图解，不替换整单图谱，不改判定保存路径。 |
| 勾选跨页留在页面状态，目前只在 `orderId` 变化时清空 | `TestOrderWorkspacePage.tsx` 的 `checkedEntryIds` | 补搜索/筛选变化清空和提示；翻页不清空，“全选”仅当前页。 |
| 删除测试单和用例时存在直接批量删除条目 | `repositories/deletion.py` | 新增条目任务清理，覆盖直接删除条目、删除测试单、删除来源用例三条路径。不能只加外键后遗留 AI 任务。 |

以上现状核对记录于阶段 1；实现改动见后续各节。控制面源码路径前缀为 `apps/control-plane/src/testing_agent/`，Worker 为 `apps/ai-worker/src/testing_agent_ai_worker/`，Studio 为 `apps/studio/src/features/test-orders/`。阶段 1 当时只作只读核对；后续测试结果见验收记录。

## 2. 技术选择及模块职责

- 任务类型固定为 `test_order_case_visualization`，阶段为 `generate`，不进入候选审核/正式资产导入。默认技能为 `mtx-analyze-case-visualization`。
- 一条执行条目对应一个稳定 AI 任务，每次手动生成创建一个执行和一个尝试；批量只是多个单条提交的聚合，不让模型一次分析整个测试单。
- 在 `domain/case_visualization.py` 放冻结输入、指纹及产物校验的纯规则；小接口 `build_input(entry)`、`validate_artifact(frozen_input, result)` 返回类型明确的结果，不提交事务、不访问模型。
- 在 `services/test_order_case_visualization.py` 提供读取、提交及发布行为，隐藏授权、绑定、去重和有效版本处理；查询与锁封装到对应 repository。HTTP handler 不访问 ORM。
- Worker 增加 `tasks/case_visualization/`，通过现有 `agent` 门面运行，不直接依赖 Nanobot/Pi，不直写业务数据库。
- Studio 在 `features/test-orders` 内新增独立图解模块，以快照、有效图解、选中步骤和原文定位回调作为输入；任务请求与视图偏好由 hook 管理。页面只负责装配。
- 不为四种图块建立通用画图平台，也不把模型坐标当语义；先用固定的受约束布局，复用既有图形依赖仅在确有需要时采用。

## 3. 身份、冻结输入与协议

| 标识 | 用途与可信来源 |
| --- | --- |
| `orderId` / `executionEntryId` | 测试单 / 执行条目的业务 ID，控制面校验归属。不是用例库 `caseId`。 |
| `taskId` | 平台稳定 AI 任务 ID；Worker 的顶层 `taskId` 另指队列任务 ID，保持既有协议，不能互换。 |
| 浏览器 `runId` | `AiExecution.execution_id`；内部 Worker 使用 `attemptId`，按 ADR 0010 保持映射。 |
| `snapshotHash` | 控制面规范化正文后计算的 SHA-256；不包含实时标题、执行结论和人员分配。 |
| `requestId` | 同一次提交与网络重试复用的客户端随机身份；服务端绑定操作人、范围、模式、连接和输入签名。 |
| `artifactId` | 直接使用产物所属 `attemptId`，不再产生第二个无关联版本号。 |

冻结内容使用 `CaseContent` 严格验证，序列化采用 UTF-8、对象键排序、无额外空白、数组顺序不变、不裁剪正文；哈希输入包括规范化算法版本 `case-content/1`。模型输入为服务端冻结的正文、执行条目身份、允许的 Schema 版本和图块类型。原文引用目录由平台确定，例如 `p0/a0/e0`；缺失的字段不生成伪来源，空预期不能作为有效断言依据。

输入放在 `attempt.input_snapshot_json.config.visualizationInput`；`source` 保存测试单/条目身份与 `snapshotHash`。不接受浏览器上传替代快照的正文，也不根据 Worker 回显身份重新绑定。

平台产物及尝试元数据记录快照哈希、协议版本、模型标识、实际技能摘要、生成时间。技能摘要来自下载与校验链路，模型名称来自实际授权配置；不要求 LLM 填写可信元数据。技能发布和领取之间可能更新，必须记录实际使用版本；不能误记为提交时版本。记录摘要用于追溯，不承诺恢复已被覆盖的旧技能。

输出分为 `ready` / `partial` / `unsupported`，语义依需求第 8.3 节。首期 `visuals.kind` 仅 `options/interval/state/quantity`。JSON Schema 以技能目录的版本化资源为源，控制面和 Worker 使用打包副本及同一套 fixture，自动检查内容摘要一致；不让控制面运行时导入 Worker 包，三个应用保持独立构建。Schema 与引用/状态规则均需验证，前端未知版本回退。

## 4. 持久化与有效产物

新增 `test_order_entry_visualizations` 绑定表。`ai_generate_tasks.execution_entry_id` 同时记录稳定条目归属（其他任务为空），供删除时直接锁任务而不提前锁绑定；真实 MySQL 测试曾发现联表锁绑定会与回传死锁，已改为该单表当前读。

| 字段 | 约束及含义 |
| --- | --- |
| `id` | 内部主键。 |
| `entry_id` | 唯一；引用执行条目，条目删除时清理绑定。 |
| `task_id` | 唯一；绑定本条目的稳定 AI 任务，不通过整单 `get_task_by_order_type` 读取。 |
| `effective_attempt_id` | 可空；当前可用图解所在尝试。失败、运行中及 `unsupported` 不修改该指针。 |
| `effective_snapshot_hash` | 可空，与有效指针一起原子更新，读取时必须匹配当前快照。 |
| `created_at/updated_at` | UTC 创建/更新时间，按模型与迁移要求填写中文注释。 |

正文唯一存放在 `AiGenerationAttempt.output_content`，格式为 JSON；绑定表不重复保存正文。任务、执行、尝试和队列沿用现有模型。结果摘要只放产物状态、版本、数量和安全错误信息；列表不带完整图解或快照。

有效产物读取需要同时确认：条目存在且归属合法、快照匹配、尝试属于绑定任务、产物版本受支持、校验通过且状态为 `ready/partial`。不能仅凭指针非空开放切换。最新运行状态和有效产物分别返回。

历史产物随现有执行记录保留，不新增按时间自动清理和历史管理 UI；首期通过当前图解与最新运行查询满足需求。绑定和任务随所属条目生命周期清理，不影响原始用例及人工判定。已有通用删除接口若能访问该新类型，必须接入专用清理/指针维护或明确拒绝，不能允许删除当前有效尝试后留下悬空指针。[ADR 0009](adr/0009-auxiliary-ai-history-deletion.md) 的旧图谱/报告接口行为不变。

新增迁移 `20261114_0003_case_visualization.py` 接在 `20261113_0002` 后，不修改 v1 baseline。本工作区已有未提交接口库迁移，不能预先复用其 revision 或覆盖它；实现时检查是否单 head。

## 5. 浏览器接口约定

所有接口使用 `/v1` 与现有 `code/message/data` 信封、显式响应模型和 camelCase；新增请求拒绝未知字段。

| 方法与路径 | 输入 | 结果 |
| --- | --- | --- |
| `GET /test-orders/{orderId}/entries/{entryId}/visualization` | 路径身份 | 当前有效产物（含正文）及最新运行摘要；从未生成时两者为 null。 |
| `POST /test-orders/{orderId}/entries/{entryId}/visualization/runs` | 必填 `requestId`、`connectionId`、`mode=generate/regenerate` | `disposition=queued/existing_active/skipped_available`、`runId` 及摘要；失败重试使用新的 requestId，网络重试复用原值。 |
| `POST /test-orders/{orderId}/visualization-batches` | `requestId`、`connectionId`、去重后的 `entryIds` | 固定的批次身份和逐条接收结果；批量始终跳过已有可用图解，不提供批量强制再生成。 |
| `GET /test-orders/{orderId}/visualization-batches/{batchId}` | 批次身份 | 有界逐条结果和汇总，不返回图解正文；完成状态区分 ready/partial/unsupported。 |
| `POST /test-orders/{orderId}/visualizations/lookup` | 有界 `entryIds` | 当前页/已选条目的图解与任务摘要，避免逐条请求及列表携带大字段。 |

单条响应设计示意：

```json
{
  "executionEntryId": "entry-001",
  "snapshotHash": "platform-computed-sha256",
  "effectiveArtifact": {
    "artifactId": "attempt-old",
    "runId": "execution-old",
    "schemaVersion": "1.0",
    "status": "partial",
    "content": {}
  },
  "latestRun": {
    "runId": "execution-new",
    "status": "failed",
    "artifactStatus": null,
    "errorCode": "visualization_generation_failed"
  }
}
```

此处 `content={}` 只说明响应外壳，不是合法图解样例；阶段 2 提供完整 Schema 样例。`effectiveArtifact=null` 与 `latestRun=null` 分别表示无当前有效产物、无运行；`artifactStatus=null` 表示本次尚无合法分析结果。

读接口使用 `read`；提交使用 `execute` 并检查测试单、条目归属及操作人本人的模型授权。执行人分配限制属于人工判定，不套用到辅助图解生成。后台领取、访问凭据、回传时复核当前权限与资源身份；特别覆盖运行中降为只读、成员移除和个人授权撤销。通用 `authorize_worker_actor` 当前调用默认 `read`，新任务需显式校验 `execute`，不能据此假定现有通用逻辑已经满足新任务。

批次做顶层测试单权限与模型授权校验；不可访问的外部条目返回统一不可用原因，不能暴露其他项目数据。顶层失败不创建任务；通过后逐条处理，删除、超限等失败不阻断其他条目。

## 6. 事务、并发与删除

1. 单条提交先校验权限与快照。在同一事务内创建/获取唯一绑定任务、保留请求身份、调用现有阶段派发并创建队列行；提交后才可领取。唯一约束兜底首次并发创建，不能只做写前查询。
2. 相同 requestId 及相同参数重放原执行，参数不同拒绝；不同 requestId 但本条目已有活跃尝试时返回已有任务，不额外调用模型。新快照未来如获支持，必须先失效/结束旧快照任务，不借用旧任务。
3. 回传沿用 Worker 身份、租约、队列、active attempt 核对。通过独立产物校验后，在同一事务完成队列和尝试终态，以及有效指针更新；不能先提交成功再异步更新指针。
4. `unsupported` 保存合法结果并结束任务，但不更新有效指针；非法结构/引用变为明确失败，旧产物不动。错误的 Worker 成功回传需要可终结的协议处理，不能无限重试同一非法正文；鉴权或身份不匹配仍按既有拒绝规则处理。
5. 重复终态回调不能重新发布、复活任务或改写结果。复用既有事件重放规则，在有效版本发布处增加幂等保护；回传失败不允许重新执行模型。
6. 锁遵循现有“队列先于阶段/尝试”；图解绑定锁放在阶段/尝试之后。派发复用现有 queue identity reservation 与 NOWAIT 冲突处理，禁止持有绑定锁再等待 Worker 已持有的队列锁。
7. 删除锁定所属业务资源后，先收集并清理关联 AI 任务的队列、阶段、尝试、绑定，再删除条目。Worker 完成过程中不新增与删除路径逆序的父资源写锁。必须针对真实 MySQL 验证首次派发/删除、回传/删除、重试/回传的锁交错；若现有辅助方法的锁序冲突，在新任务适配处调整，不能仅凭此设计声明无死锁。
8. 首期正文不支持在线更新。对已有快照作新鲜校验并拦截不匹配结果；若未来新增更新快照接口，必须在同一事务失效有效指针并与图解发布串行化，不只添加读时比较。

批量阶段采用轻量批次记录与逐条结果映射，不另建模型批处理引擎。批次唯一键绑定操作人、测试单及 requestId；固定 entryIds 与请求签名，逐条保存接收结果/执行身份。实现采用一次有界事务原子保存批次与队列，逐条可预期拒绝用 savepoint 隔离；意外进程失败整体回滚，同 requestId 重试恢复提交。回执存入 `test_order_visualization_batches`，已接收条目复用原执行，包括已跳过条目不能因重放变成新生成。批次最多 100 条，查询一次返回该有界集合，无额外分页。

## 7. Worker 与技能接入

- 控制面同步新增 `domain/ai_tasks.py` 任务映射与辅助类型、任务归属验证、新默认 Skill、删除分类及图解专用 completion；不改变旧类型解析。
- Worker 同步更新 `skill_names.py`、`platform/skills.py::TASK_SKILLS`、`worker/dispatcher.py`、`app/bootstrap.py`，新增执行器、输入解析、输出校验与行为测试。
- Worker 从 `configJson.visualizationInput` 读取冻结内容；TaskSource 的已有原始快照/配置承载可复用，新增严格业务模型放在新任务模块，避免污染全局 `Task`。
- Skill 只做语义分析及结构化输出，不执行测试、不访问被测系统。运行时不授予浏览器或外部操作工具，输入正文被视为待分析材料而非指令。
- 实际技能清单摘要与模型信息通过受限 Worker 元数据记录，模型输出不写这些值。通用辅助 completion 目前会丢弃 output context，本任务适配必须明确接收并核对这些信息。
- 生成失败采用用户手动重试；只复用已有传输层重试，不新增隐式语义重生成循环。模型超时和心跳遵守当前 backend/queue 配置，新增任务不另设与其冲突的等待逻辑。

## 8. Studio 接入与视图状态

- `TestOrderWorkspacePage` 保留顶部“用例执行/用例图谱”；“文字/可视化”仅作为用例执行内部显示模式。
- 新增 `useCaseVisualization` 管任务与产物查询，新模块渲染四类图块；`TestOrderCaseContent` 仍可作为文字回退入口。判定按钮、保存 hook、缺陷关联及草稿不因视图切换重建。
- `preferredMode` 记录本次浏览选择；实际显示模式由条目有效产物决定。回退文字不改偏好；进入/刷新重置文字。任务完成只使切换可用，不自动改变当前展示。切换条目时才按已保留偏好选择展示；显式切换始终优先。
- 选中步骤只高亮对应图形与更新右侧完整原文；稳定 ID 为快照身份加步骤索引。切换图解版本时不得让旧来源索引定位到别的快照。
- 来源定位支持前置条件、操作、预期及多个引用；来源文本只从当前冻结快照读取。图形文字普通转义，不渲染模型 HTML/脚本/外链。
- 部分覆盖提示常显；操作中的检查要求独立标注且提示预期缺失，不形成正式验证焦点。
- 跨页勾选沿用页面集合；搜索/筛选变化时清空并提示，隐藏执行区时继续停用人工判定快捷键。仅对活动任务轮询，停止/失败/完成后结束轮询；不为整单每条图解逐个轮询。
- 样式使用现有 token、滚动高度链和窄屏布局；实现阶段应用 `impeccable` 技能及界面规范，并做真实浏览器验证。原型只作为参考，不直接复制其模拟平台行为。

## 9. 工程上限与验证基线

下列是阶段 2 起采用的初始工程参数，不是用户承诺的模型性能；边界失败必须明确返回，不能静默截断。若样本验证发现不适用，调整契约版本及所有消费方并记录原因。

| 项目 | 初始约定 |
| --- | --- |
| 批量/摘要查询 | 每次最多 100 条；UI 显示限制，服务端强制校验，重复 ID 去重。 |
| 模型输入正文 | 规范化 UTF-8 JSON 最多 256 KiB；超限保持文字并提示，不截断快照。 |
| 图解输出 | 最多 512 KiB、8 个图块、100 个实体、200 条关系、100 个断言；单个生成文本最多 4000 字符，结构深度最多 12。完整原文不受生成标签长度裁剪。 |
| 并发 | 复用 Worker `max_concurrent_tasks`（当前默认 2），每条目最多 1 个活跃尝试；批量不在进程内额外开启模型并发池。 |
| 时间与重试 | 复用当前 backend 超时及队列租约；请求传输重试复用 requestId，模型失败不自动重跑。 |
| 版本保留 | 不增加定时清理；随业务资源删除清理，具体存储遵守现有 AI 执行生命周期。 |

交付前验证：

- 控制面：严格 Schema、来源与快照哈希、跨项目/角色/授权撤销、重复提交、旧产物保留、非法回传、迟到结果、三条删除路径、迁移及真实 MySQL 并发。
- Worker：技能获取和摘要、分派、严格输入输出、缺失/否定/条件/数量、unsupported 与失败区分、回传重试不再调用模型。
- Studio：模式状态转换、生成完成不抢视图、来源联动、跨页勾选与筛选清空、部分覆盖及降级、旧判定功能回归；类型/Lint/主题/构建及浏览器尺寸和键盘检查。
- 真实模型：至少 50 条人工标注样本，覆盖首期类型与异常；严重错误 0，人工认定适用样本的有效覆盖率至少 80%。报告分子/分母及部分覆盖判定，不以模型自评替代人工评审。
- 若修改平台配置或编排，追加根目录 unittest 和 `scripts/manage.py compose config --quiet`；不修改编排时不为了本功能改运行入口。

## 10. 阶段交付状态

- [x] 核对快照、身份、权限、任务派发/回传、技能获取、删除及工作台入口。
- [x] 确定任务粒度、模块职责、有效产物与最新运行分离、请求与版本身份。
- [x] 明确接口、初始上限、兼容点及后续工单。
- [x] 阶段 2：机器 Schema、共享引用校验、四类完整样例及反例测试。
- [x] 阶段 3～6：控制面、Worker、Studio 和批量实现及专项验证。
- [ ] 阶段 7：MySQL 专项及组件浏览器验证已完成；真实模型、50 条人工标注和语义评审未完成。

当前无须重新确认已完成的产品决策。工程默认值由样本和实现验证；涉及新增产品行为、扩大权限或改变已确认规则时再逐项询问。已有未提交接口库改动和原型文件均保持不动。

## 实现文件导航

- [机器协议](../../apps/control-plane/default-skills/mtx-analyze-case-visualization/references/output.schema.json)、[纯校验规则](../../apps/control-plane/src/testing_agent/domain/case_visualization/contract.py)。
- [浏览器请求/响应模型](../../apps/control-plane/src/testing_agent/schemas/case_visualization.py)、[路由](../../apps/control-plane/src/testing_agent/routers/case_visualization.py)、[业务编排](../../apps/control-plane/src/testing_agent/services/test_order_case_visualization.py)。
- [Worker 完成事件](../../apps/control-plane/src/testing_agent/services/case_visualization_completion.py)、[数据库模型](../../apps/control-plane/src/testing_agent/models/case_visualization.py)、[迁移](../../apps/control-plane/alembic/versions/20261114_0003_case_visualization.py)。
- [Worker 运行及质量验收说明](../ai-worker/case-visualization.md)、[Studio 交互说明](../studio/case-visualization.md)。

协议资源以机器文件为准：首期区间绘制均为非比例示意，已明确的端点、单位和开闭边界可用实体 `range` 显示；未知项为 null，不推算。模型 `summary` 不代替原始标题或预期。
