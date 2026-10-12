# 平台内置 Bug 资源与禅道缺陷并存

第一版 Bug 管理在平台内部独立建账（`bugs` / `bug_activities` 两张表，`/v1/projects/{projectId}/bugs`
系列接口），**不改写 ADR 0001 的「禅道继续作为缺陷来源」**：`test_order_entries.zentao_bug_id`
保留原语义，执行判定区在展示平台 Bug（按 `source_entry_id` 关联查询）的同时继续支持填写
禅道缺陷号；`sprint_daily_metrics` 的缺陷统计仍来自禅道采集，暂不混入本地 Bug。
迁移策略待本地 Bug 数据积累后再评估是否并轨。

**关键取舍**：

1. **项目内自增编号**（`uk_bugs_project_bug_no`，展示为 `BUG-{bugNo}`）。这是平台第一个
   人类可读编号机制（其余实体全部 uuid），创建时事务内 max+1、唯一键冲突重试三次；
   编号可搜索、可口头引用，是 Bug 之间的主要沟通方式，uuid 无法承担。
2. **迭代 / 需求 / 执行来源用业务键引用、不建外键**。Bug 是跨迭代长期存在的记录，
   而迭代删除会被需求 / 测试单阻塞（ADR 0003 的物理删除链），若 Bug 的 `found_sprint_id`
   建外键，任何引用过的迭代都删不掉，形成死锁。因此 Bug 保留引用值，展示层解析失败时
   回退为「未关联」；执行来源（测试单 / 条目 / 用例）在建 Bug 时快照名称
   （`source_order_name` / `source_case_title`），来源被删后仍可读，点击跳转 404 可接受。
3. **多轮历史全保留**（`bug_activities`，kind = status_change / transfer / comment / edit /
   attachment）。需求文档要求多轮修复、回归、拒绝、重开的记录不覆盖，这是平台第一张
   审计性质的表；它与 ADR 0003「删除即物理删除」不冲突——表记录的是业务过程，不是删除日志。
4. **六状态机**：pending（待确定）→ processing（处理中）→ pending_regression（待回归）→
   closed（已关闭），rejected（已拒绝，必填三选一原因）、reopened（重新打开）为独立状态；
   不设「已确定」。流转表定义在 `services/bug.py`，服务层内联校验（与 test_order_entry 同模式）。
   「未关闭」快捷筛选口径为不含已关闭与已拒绝。

**权限默认**（需求文档未定，按最小约定落地）：读 = 项目 read；创建 / 编辑 / 流转 / 转派 /
评论 = 项目 write；责任人可选范围 = 项目成员（含所有者），转派不改状态、创建人不随转派变化。
附件复用统一文件管线（`docs/control-plane/file-storage.md` 预告的 purpose=`attachment`、
`resource_type="bug"`）。

## 开发成员权限补充（2026-10-03）

根据已确认的开发成员需求，替换上述权限默认：查看 Bug 与处理记录要求 `bug_read`；
评论、转派和状态流转要求 `bug_handle`；创建和编辑基本信息继续要求 `write`。
所有者与普通成员保留全部 Bug 操作，只读成员保留查看，开发成员仅获得查看与处理。
开发成员不继承全项目 `read`，项目选择所需信息使用独立 `project_read` 权限。

Bug 筛选与转派通过 `/v1/projects/{projectId}/bugs/options` 获取成员、迭代的 ID 和名称，
不授予完整成员或迭代资源的读取权限。文件下载仅对已关联到 Bug 的附件开放；其他文件
仍要求全项目读取权限。开发成员看得到 Bug 的关联名称，但不能跳转读取需求或执行记录。
普通成员降为开发成员时使其未完成任务失效；普通成员降为只读成员时继续保留已有操作的
原有语义。迁移 `20261003_0022` 扩展成员角色约束，降级前必须先调整现存开发成员。

## 状态模型调整（2026-10-06）

本 ADR 的第 4 项六状态机由 [ADR 0005](0005-bug-zentao-lifecycle.md) 替代，其他关于独立 Bug 资源、编号、关联与完整历史的决策继续适用。

## 迭代缺陷统计切换（2026-10-08）

按用户要求，迭代概览与测试报告的缺陷快照改用平台 Bug 列表数据，替代本 ADR 与 ADR 0001 中保留禅道缺陷来源的约定。筛选为当前项目和发现迭代，不按计划修复迭代统计，也不额外合并远端缺陷，避免重复计数；无需个人禅道授权。

更新数据时，active/resolved/closed 分别计入未解决/已解决/已关闭；解决方案不改变主状态统计，已解决不代表已修复。fatal/serious/normal/minor 分别对应现有 fatal/serious/normal/suggestion 响应字段。报告明细冻结 bugId（平台业务标识）、bugNo（项目内编号）、title、status、severity、resolution 摘要，不读取正文和历史。

成功查询空列表保存零；查询失败使更新失败，不提交伪零快照。历史快照与历史未采集状态保留，只有显式重新生成才采用新口径，趋势不倒推重建。接口字段和快照读取行为保持兼容。
