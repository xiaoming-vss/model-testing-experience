import { AnalysisDetailPanel as RulePanel, AnalysisDetailValue as RuleValue } from './AnalysisDetailPanel'

export function AnalysisRuleDetails({ item }: { item: Record<string, unknown> }) {
  return <div className="ai-analysis-rule-layout">
    <RulePanel title="适用范围">
      <div className="ai-analysis-rule-scope">
        <div><span>规则分类</span><RuleValue value={item.category} /></div>
        <div><span>适用对象</span><RuleValue value={item.applicableObject} /></div>
      </div>
    </RulePanel>
    <div className="ai-analysis-rule-pair">
      <RulePanel title="前置条件"><RuleValue value={item.preconditions} list /></RulePanel>
      <RulePanel title="触发操作"><RuleValue value={item.trigger} /></RulePanel>
    </div>
    <RulePanel title="预期行为" emphasis><RuleValue value={item.expectedBehavior} list /></RulePanel>
    <div className="ai-analysis-rule-pair">
      <RulePanel title="禁止或跳过的行为"><RuleValue value={item.prohibitedOrSkippedBehavior} list /></RulePanel>
      <RulePanel title="可观察结果"><RuleValue value={item.observableOutcome} list /></RulePanel>
    </div>
    <RulePanel title="来源与关联">
      <div className="ai-analysis-rule-sources"><span>来源依据</span><RuleValue value={item.sourceReferences} list /></div>
      <div className="ai-analysis-rule-questions"><span>关联待确认项</span><RuleValue value={item.relatedQuestionIds} list /></div>
    </RulePanel>
  </div>
}
