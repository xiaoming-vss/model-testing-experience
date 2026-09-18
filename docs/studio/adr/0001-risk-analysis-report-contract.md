# 风险分析报告条目级字段契约由 testpilot-studio 规范定义,worker 按此实装

`code_risk_analysis` 在 ai-worker 侧尚未实装,control-plane 的 `parse_risk_report` 只校验顶层区块键与 repositories 条目(`repositoryId/branch/baselineCommit/headCommit`),条目级字段宽类型透传、不校验。测试夹具中的示例字段(`changeOverview` 为全局数字、`affectedCases` 无套件/集合字段)与 RS-4 的展示要求(按仓库分组 diffstat、受影响用例含套件/集合)冲突,故现在由 Studio 规范补全条目级契约,worker 将来按此实装,避免先开发后对齐的返工:

- `repositories[]` 条目增加 `filesChanged`/`additions`/`deletions`(每仓库 diffstat 数字);`changeOverview` 保留为全局汇总。control-plane 保留未知扩展字段,前端契约字段可直接透传,后端无需改动。
- `affectedCases[]` 条目增加 `suiteId`/`suiteName`(用例所属套件/集合)。
- `risks[].level` 取值 `high`/`medium`/`low`,前端映射高/中/低色标展示。
- 契约写入 `docs/studio/specs/code-binding-risk-analysis.md`(03)并同步 `.scratch/code-binding-risk-analysis/02-ai-worker.md`(02)。

**Considered Options**: 严格按测试夹具字段渲染(放弃「按仓库分组」与「套件/集合」展示,worker 实装时字段以它为准);先按夹具开发、worker 实装后再对齐(字段可能不一致导致前端返工)。
