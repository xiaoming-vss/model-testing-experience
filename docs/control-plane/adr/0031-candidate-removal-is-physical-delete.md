# ADR 0031：删除候选是物理删除

- 状态：已接受
- 日期：2026-11-26
- 取代：[生成候选实施规格](../../records/2026-11-20-generation-candidates-spec.md) 中“丢弃保留快照供审计”的相关描述，以及 [ADR 0025](0025-independent-stage-adoption.md) 后果中“候选被拒绝/丢弃/缺失”的“丢弃”；[ADR 0024](0024-generation-candidates-current.md) 决策 10 的“不自动删除、不设保留期”继续有效，仅新增手动删除语义
- 被取代：决策 2 中的候选状态限制自 2026-11-27 起由 [ADR 0037](0037-rejected-candidate-deletion.md) 取代
- 关联：[生成链现状](../generation-chain.md)、[数据库结构](../database-schema.md)、[ADR 0024](0024-generation-candidates-current.md)、[ADR 0025](0025-independent-stage-adoption.md)

## 背景

候选处置此前分为 `rejected` 和 `discarded` 两种状态，两者都只写入处置状态，保留候选行、正文和来源快照。实际使用中，用户只需要表达“不要这个候选”；保留下来的已丢弃候选仍会出现在候选列表和分页中，并继续显示“已丢弃”，没有对应的审计收益。

## 决策

1. 单候选处置接口的 `action` 由 `reject | discard` 改为 `reject | delete`。`reject` 保留：写入 `rejected` 状态并轮换候选令牌；`delete` 物理删除 `ai_generation_candidates` 行。
2. 只允许删除 `available` 且不是当前采用内容的候选。当前内容指针 `ai_generation_stage_contents.source_candidate_id` 仍由外键和业务校验保护。
3. 删除前把子候选的 `derived_from_candidate_id` 置空，保留子候选的正文、状态和来源快照；不级联删除派生候选。
4. 删除时把该候选当前 attempt 标记为 `invalidated_reason = "审核未通过，候选产物已删除"`，运行历史继续显示审核未通过，不把已处理的尝试退回待审核。
5. 幂等回执、采用回执和 `ai_generate_imports` 继续保留 candidate/snapshot 审计标识，不随候选删除而删除。
6. 移除 `discarded` 状态；候选接口只返回 `available` / `rejected`，预发布阶段不保留该状态的只读兼容。
7. 不增加自动清理或保留期；只有用户显式删除才会物理删除。不修改 Alembic 基线：处置列仍是字符串，取值由应用层约束。

## 后果

- 删除后候选从列表和详情消失，阶段的待处理候选数自然减少。
- 下游冻结来源引用被删候选时，来源解析返回 `source_unknown`，仍会阻止继续使用；这与拒绝导致的 `source_stale` 一样属于来源失效。
- 删除曾采用或导入过的旧候选后，对应运行历史显示为审核未通过/已删除；正式用例、导入回执和审核回执不受影响。
- 删除与采用、编辑、派生和生成之间的并发安全仍由候选令牌、槽位令牌、事务锁和请求回执保证，不新增阶段活动门禁。
- 历史规格与记录保留为证据，不作为现行行为依据；本 ADR 明确覆盖其中“丢弃保留快照”的部分。
