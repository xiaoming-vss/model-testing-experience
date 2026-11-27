# ADR 0038：完整用例生成前归并测试点和核对历史覆盖

- 状态：已接受
- 日期：2026-11-26
- 取代：—
- 被取代：—
- 关联：[ADR 0025](0025-independent-stage-adoption.md)、[ADR 0029](0029-historical-test-case-verification-stage.md)、[ADR 0030](0030-historical-supplemental-test-points.md)

## 决策

「完整用例」在启动时将已采用的历史用例核验作为可选的直接上游，连同该候选的核验输入冻结进 `config.historyCasePlanning`。已有试生成仍可只提交两个必选来源，控制面补入当前历史核验。如同时选用了历史核验与功能测试点，来源闭包要求两者基于同一材料整理候选。已有运行快照和没有历史核验的需求沿用原派发。

AI Worker 先用 `mtx-plan-functional-case-generation` 对本轮全部点做一次匹配。条件、操作和可观察结果等价的点归为一个目标。每个输入点恰属于一个目标。有效的旧用例完整覆盖才复用；仅部分覆盖的点按整点判断。明确对应整点的需修改结论记为待修订，尚未覆盖。建议失效的旧用例仍展示依据，其场景是否要补测按本次规则判断。每个待写目标只派给一个模块；模块并发上限沿用 2。

模型批次临时返回 `generationTargetId`，Worker 校验模块归属及测试目标全集并将它换成 `sourcePoints`。候选正文附 `historicalCaseFindings`，按核验批次保留最终的可复用、需修改和建议失效结论及所关联的点。全复用允许 `cases: []`。正式资产导入读取 `cases`，历史结论供用户在用例库确认。

## 发布

先同步两个默认 Skill，再升级 AI Worker，最后升级控制面和 Studio。旧的无规划批次继续使用七字段生成协议。控制面审核和导入沿用既有候选与来源闭包。此变更不涉及数据库结构。
