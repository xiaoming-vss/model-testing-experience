# 新增 UI 测试用例生成任务并解耦候选结果审核与导入

## Problem Statement

当前控制平面已经支持 API 测试用例生成、功能测试用例生成、需求分析和测试报告生成，但缺少 UI 测试用例生成任务。用户无法通过与 API 用例生成一致的方式创建任务、下发给 AI Worker、审核候选生成结果并导入正式 UI 测试套件。

现有用例生成任务还把“审核通过”和“导入成功”绑定在同一个操作中。目标集合或套件存在同名用例时，导入冲突会阻断审核，用户也无法先查看新旧完整用例差异再决定是否覆盖。运行响应使用 `importedCollectionId` 表达导入目标，该字段不能正确描述 UI 测试套件或一次涉及多个功能测试套件的导入。

## Solution

新增 `taskType=ui_case_generate` 的 UI 测试用例生成任务。它复用 API 用例生成任务的创建、查询、修改、删除、运行、Worker 下发和运行查询生命周期。AI Worker 负责具体生成过程，控制平面负责保存候选生成结果、人工编辑与审核、导入冲突预览、确认覆盖以及导入状态记录。

统一调整功能、API、UI 三类用例生成任务：审核与导入成为两个独立操作。成功运行的候选生成结果可在待审核阶段编辑；审核通过后冻结。只有成功且审核通过的运行才能导入。导入遇到目标内同名用例时，先返回新旧完整内容且不写入数据；用户确认后再次调用，服务端重新检查并整批新增或原位覆盖。同名用例覆盖时保留已有用例 ID。导入失败、取消或冲突预览均不改变审核结论。

删除 `importedCollectionId`，统一使用 `importStatus`、`importedTargets` 和 `importedAt` 表达导入状态与一个或多个目标，并尽最大可能迁移历史数据。

## User Stories

1. As a 测试负责人, I want to create a UI 测试用例生成任务, so that UI 自动化用例可以进入现有 AI 生成工作流。
2. As a 测试负责人, I want UI 生成任务使用与 API 生成任务一致的创建参数, so that 前端和调用方不需要学习另一套任务模型。
3. As a 测试负责人, I want to list, inspect, update and delete UI 生成任务, so that 我可以管理项目中的 UI 生成工作。
4. As a 测试负责人, I want to run a UI 生成任务 with an LLM connection, so that 控制平面可以把任务下发给 AI Worker。
5. As an AI Worker, I want to claim `ui_case_generate` through the existing AI Worker contract, so that Worker 无需接入新的调度体系。
6. As an AI Worker, I want the run snapshot to contain the same task context fields used by API generation, so that 我可以获得项目、迭代、需求、来源内容和指令。
7. As an AI Worker, I want to return candidate UI cases under a `cases` root array, so that 控制平面可以稳定解析一批候选用例。
8. As a reviewer, I want each candidate UI case to contain `name`、`enabled`、`orderNo` and `stepsJson`, so that 审核内容能够直接对应正式 UI 测试用例。
9. As a reviewer, I want each UI step to retain Worker-supported fields such as `orderNo`、`stepName`、`keyword`、`locatorType`、`locatorValue`、`operationValue`、`continueOnFailure` and `enabled` when applicable, so that 审核通过的内容可以直接导入。
10. As a reviewer, I want to edit candidate cases while review is pending, so that 我可以删除重复项并修正名称、步骤或请求内容。
11. As a reviewer, I want approval to freeze the final candidate result, so that 后续导入使用的内容与我批准的内容一致。
12. As a reviewer, I want only successful runs to be approvable, so that 失败、错误或取消的生成运行不会形成无效批准。
13. As a reviewer, I want approval and import to be independent actions, so that 导入冲突或失败不会改变审核结论。
14. As a user, I want only approved successful runs to be importable, so that 未经审核的候选结果不能进入正式测试资产。
15. As an API test owner, I want to select an existing API collection as the import target, so that approved API cases enter the intended collection。
16. As a UI test owner, I want to select an existing UI test suite as the import target, so that approved UI cases inherit the intended执行配置。
17. As a function test owner, I want generated function cases to continue resolving target suites from modules, so that one result can populate multiple suites。
18. As a user, I want an import without conflicts to complete in one request, so that 正常导入不增加额外交互。
19. As a user, I want an import with name conflicts to return `requiresConfirmation` and make no mutation, so that 我可以先做决定。
20. As a user, I want every conflict to include complete `existingCase` and `generatedCase` objects, so that 我可以比较新旧用例的所有重要内容。
21. As an API test owner, I want API comparisons to include request data, headers, query, body, extraction rules and assertion rules, so that 覆盖决定基于完整信息。
22. As a UI test owner, I want UI comparisons to include the full case and every `stepsJson` field, so that 定位器、操作值和失败策略均可比较。
23. As a function test owner, I want function comparisons to include the complete old and new manual case content, so that 前置条件、步骤和预期结果均可比较。
24. As a user, I want names compared after trimming and without case sensitivity, so that 预检与数据库唯一性规则一致。
25. As a user, I want to confirm overwrite in a second request, so that 覆盖是明确的人工决定。
26. As a user, I want the server to recheck conflicts upon confirmation, so that 预览后发生的数据变化不会被忽略。
27. As a user, I want confirmed conflicts to update the existing case in place, so that case ID 和已有引用保持稳定。
28. As a user, I want non-conflicting cases inserted in the same confirmed import, so that 整批结果一次落库。
29. As a user, I want the whole import to be atomic, so that 不会出现部分导入状态。
30. As a reviewer, I want canceled, failed or conflicted imports to preserve approved review status, so that 审核事实不被导入结果改写。
31. As a user, I want a generation run to be successfully imported only once, so that 同一批结果不会重复覆盖或散布到多个目标。
32. As a user, I want failed or canceled import attempts to remain retryable, so that 临时问题不会永久阻止导入。
33. As a user, I want run responses to expose `importStatus`、`importedTargets` and `importedAt`, so that 任意测试资产类型的导入状态都能被准确表达。
34. As a function test owner, I want `importedTargets` to support multiple suites, so that 多模块结果不会被压缩成有损字符串。
35. As an existing user, I want historical import targets migrated where possible, so that 升级后已有导入记录仍然可查询。
36. As a project owner, I want all task, review, comparison and import operations to enforce ownership, so that 其他用户不能读取或覆盖我的测试资产。
37. As an API client maintainer, I want OpenAPI and route contracts updated, so that 客户端可以依据准确契约升级。

## Implementation Decisions

- 新增 UI 生成任务类型 `ui_case_generate`，复用现有通用 AI 生成任务与运行模型。
- UI 任务创建参数与 API 生成任务一致：`name`、`sprintId`、`requirementId`、`sourceType`、`sourceContent`、`instruction`。
- UI 运行继续复用现有 LLM 连接、触发类型、配置和 Worker 调度机制。
- 控制平面不设计 AI Worker 如何生成步骤、探索页面或构造 locator，只传输并持久化结果。
- UI Worker 结果最外层为 `cases` 数组；每项包含完整候选 UI 用例。
- UI 步骤遵循 Worker 现有契约。只有需要元素定位的操作才包含 `locatorType`、`locatorValue`；`open`、`sleep` 等操作可省略。
- UI 任务公开接口完整覆盖创建、列表、详情、修改、删除、运行、运行列表、运行详情和审核。
- 功能、API、UI 生成运行共享候选结果修改能力，只允许在 `reviewStatus=pending` 时修改。
- 候选修改直接替换当前结果，不新增版本表、版本恢复或差异历史。
- 审核通过后冻结候选结果；只有 `status=success` 的运行允许通过审核。
- 审核与导入分离。审核通过不自动导入，也不要求集合或套件目标。
- 只有运行成功、审核通过且尚未成功导入的结果可以调用导入。
- API 导入要求一个已有 API 集合；UI 导入要求一个已有 UI 测试套件，AI 不创建 UI 套件；功能导入继续根据模块确定一个或多个功能套件。
- 同一次运行只允许成功导入一次；冲突预览、取消和失败不消耗该机会。
- 首次导入先检测冲突。无冲突时直接原子导入；有冲突时返回 `requiresConfirmation=true` 和全部冲突，本次不写数据。
- 每个冲突包含标准化名称、完整 `existingCase` 和完整 `generatedCase`。
- API 对比包含请求、请求头、查询参数、请求体、提取规则和断言规则；UI 对比包含完整 `stepsJson`；功能对比包含完整人工用例字段。
- 同名判断为去除首尾空格后不区分大小写。候选批内重名在审核阶段解决，不设计独立导入冲突流程。
- 覆盖确认使用显式 `confirmOverwrite=true`。确认时服务端重新检查当前数据。
- 确认覆盖时原位更新同名用例并保留用例 ID；非冲突项在同一事务内新增。任何失败回滚整批操作。
- 导入冲突、取消或失败不修改审核状态、审核人、审核时间或审核备注。
- 删除数据库与 API 中的 `importedCollectionId`，不提供兼容别名。
- 运行统一返回 `importStatus`（`pending` 或 `imported`）、`importedTargets` 数组和 `importedAt`。
- `importedTargets` 项包含 `targetType` 和 `targetId`，目标类型包括 `api_collection`、`ui_suite`、`function_suite`。
- 历史 API 导入目标精确迁移为 `api_collection`；历史功能套件目标尽量恢复，原压缩值无法完整恢复时明确标记迁移不完整。
- 新功能用例导入完整保存所有套件目标，不再压缩。
- 所有新接口沿用已有项目所有权和目标资产所有权检查。
- OpenAPI 与路由契约同步更新；删除旧字段是本规格明确接受的破坏性契约变更。

## Testing Decisions

- 主要测试缝为 FastAPI 应用 HTTP 契约层，通过同一应用流程覆盖公开用户接口和内部 AI Worker 接口。
- UI 主验收流程为：创建任务、运行、Worker 领取、Worker 回传 `cases`、人工编辑、审核通过、首次导入返回冲突、确认覆盖、查询正式 UI 用例与运行导入状态。
- API 与功能用例生成使用等价 HTTP 流程验证审核不再自动导入，并改用独立导入操作。
- 测试只断言外部可见响应和持久化结果，不依赖私有辅助函数或内部条件分支。
- 冲突测试验证首次请求返回完整新旧内容且零写入。
- 确认测试验证重新检查、保留用例 ID 的原位覆盖、非冲突新增以及事务回滚。
- 状态测试验证冲突预览、取消和失败后 `reviewStatus` 仍为 `approved`。
- 资格测试验证只有成功运行可以批准，只有成功且已批准的运行可以导入。
- 幂等测试验证成功导入后不能再次导入，失败尝试仍可重试。
- 名称测试覆盖首尾空格和仅大小写不同的冲突。
- 候选编辑测试验证待审核时可保存，批准后不可修改。
- Worker 契约测试验证 `ui_case_generate` 通过现有 AI Worker API 下发，并正确接受结果字段别名。
- 扩展仓库已有路由、OpenAPI 和 Go 字段契约测试。
- 数据迁移测试从含 API/功能历史导入值的数据库升级，验证精确迁移、尽力迁移、迁移不完整标记及旧字段删除。
- 只有迁移或事务失败无法通过 HTTP 可靠观察时，才补充更低层测试。

## Out of Scope

- AI 或提示词如何生成 UI 用例。
- AI Worker 是否必须访问真实网页。
- 页面探索、locator 发现或 locator 质量保证。
- 新增 UI Worker 关键字或修改 UI 执行语义。
- 自动创建 UI 测试套件或决定其视口、超时、无头模式、截图策略。
- 候选修改版本历史、差异、恢复或最终审核元数据之外的审计快照。
- 候选批内重名的专用导入冲突流程。
- 允许同一已审核运行成功导入多次。
- 保留 `importedCollectionId` 兼容字段。

## Further Notes

候选生成结果不是正式测试资产。审核是对候选质量的判断；导入是把已批准内容物化为正式测试资产的独立尝试。因此，导入冲突和失败不得改写审核结论。

确认的 UI 用例结构包含用例级 `name`、`enabled`、`orderNo`、`stepsJson`。步骤可按 Worker 关键字契约包含 `orderNo`、`stepName`、`keyword`、`locatorType`、`locatorValue`、`operationValue`、`continueOnFailure`、`enabled`。

本规格明确接受删除 `importedCollectionId` 带来的破坏性 API 与数据库变更；仓库内所有响应模型、OpenAPI 契约和已知调用方必须在同一变更中迁移。
