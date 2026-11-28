# 长期记录（Records）

- 状态：现行
- 负责人：platform maintainers
- 最近复核：2026-11-20
- 复核周期：每季度
- 适用范围：`docs/records/` 与 `docs/<project>/records/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行。

本目录保存需要长期追溯的规格快照、验收证据和历史设计记录。现行规范仍在 `docs/<project>/` 的正式文档中维护；记录不替代规范，也不作为当前实现的唯一依据。

## 与 `.scratch/` 的边界

- `.scratch/` 是本地工作区，默认被 git 忽略，只放进行中的草稿、工单和一次性验证产物。
- 任何需要新 clone、CI、其他 Agent 或审计人员看到的内容，必须提升为长期记录或写进现行规范。
- 规范、README、ADR 不得只链接 `.scratch/` 作为证据；引用工作区时须注明“本地工作副本，不作为长期证据”。
- 功能收尾时按[问题跟踪器](../agents/issue-tracker.md#scratch-生命周期与长期记录)的检查清单提升规格与验收证据。

## 目录与命名

| 范围 | 位置 | 命名 |
| --- | --- | --- |
| 跨项目 | `docs/records/` | `YYYY-MM-DD-<slug>.md` |
| 单项目 | `docs/<project>/records/` | `YYYY-MM-DD-<slug>.md` |

每份记录至少包含：日期、状态、负责人、来源、关联规范或 ADR。记录一旦归档不再改写结论；需要更新时新增带日期的记录并在旧记录标注被取代。

## 索引

### 跨项目

- [2026-11-20 生成链多候选与唯一当前内容实施规格](2026-11-20-generation-candidates-spec.md)
- [2026-11-20 整改复核及本地验收](2026-11-20-remediation-recheck.md)
- [2026-11-21 生成候选改造验证](2026-11-21-generation-candidates-verification.md)
- [2026-11-22 阶段采用改为独立指针](2026-11-22-independent-stage-adoption.md)
- [2026-11-22 正式用例失效标记](2026-11-22-case-invalidation.md)

### control-plane

- [2026-11-26 本地开发库元素库补表](../control-plane/records/2026-11-26-ui-element-library-local-db-sync.md)
- [2026-11-20 生成链候选改造契约与盘点基础](../control-plane/records/2026-11-20-generation-candidate-foundation.md)
- [2026-11-20 本地开发库性能运行迭代字段升级](../control-plane/records/2026-11-20-perf-run-local-db-upgrade.md)
- [2026-11-14 测试单单用例执行可视化规格](../control-plane/records/2026-11-14-test-order-case-visualization-spec.md)
- [2026-10-04 Bug 附件、正文图片与状态同步可行性分析](../control-plane/records/2026-10-04-bug-zentao-sync-feasibility.md)

### studio

- [2026-11-23 完整用例正式导入入口核对](../studio/records/2026-11-23-final-cases-import-sidebar.md)
- [2026-11-22 候选工作区独立采用视觉验收](../studio/records/2026-11-22-independent-adoption-visual-check.md)
- [2026-11-21 候选侧栏视觉验收](../studio/records/2026-11-21-candidate-sidebar-visual-check.md)
- [2026-11-20 EntityCard 颜色回归验收](../studio/records/2026-11-20-entity-card-visual-check.md)
- [2026-10-12 测试单参考图对齐验收记录](../studio/records/2026-10-12-reference-image-alignment.md)
- [2026-09-28 Bug 管理需求核对与页面整理](../studio/records/2026-09-28-bug-management-review.md)

### perf-worker

- [2026-11-20 性能运行指标与夜莺筛选规格](../perf-worker/records/2026-11-20-performance-metrics-spec.md)
- [2026-11-20 性能运行指标阶段验证](../perf-worker/records/2026-11-20-performance-metrics-validation.md)

### ai-worker

- [2026-11-14 用例可视化技能独立试跑记录](../ai-worker/records/2026-11-14-case-visualization-skill-trial.md)
- [2026-11-26 完整用例历史覆盖验证](../ai-worker/records/2026-11-26-complete-case-history-planning-validation.md)

## 维护规则

- 新增记录时同步更新本索引和对应项目 README。
- 记录中的截图、测试数量等一次性证据注明获取日期；无法长期保存的本地产物只描述存放位置，不作为审计依据。
- 记录过期但仍有审计价值时保留；确认无价值后按规范变更检查清单删除，并在变更说明中记录原因。
