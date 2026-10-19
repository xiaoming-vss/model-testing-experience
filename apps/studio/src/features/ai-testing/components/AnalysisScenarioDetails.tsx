import { AnalysisDetailPanel as Panel, AnalysisDetailValue as Value } from './AnalysisDetailPanel'

export function AnalysisScenarioDetails({ item }: { item: Record<string, unknown> }) {
  return <div className="ai-analysis-rule-layout">
    <div className="ai-analysis-rule-pair">
      <Panel title="场景条件"><Value value={item.conditions} list /></Panel>
      <Panel title="触发操作"><Value value={item.trigger} /></Panel>
    </div>
    <Panel title="验证目标" emphasis><Value value={item.verificationObjective} list /></Panel>
    <div className="ai-analysis-rule-pair">
      <Panel title="推导类型"><Value value={item.derivationType} /></Panel>
      <Panel title="阻塞原因"><Value value={item.blockingReason} list /></Panel>
    </div>
    <Panel title="关联依据">
      <div className="ai-analysis-rule-scope">
        <div><span>关联规则</span><Value value={item.relatedRuleIds} list /></div>
        <div><span>关联待确认项</span><Value value={item.relatedQuestionIds} list /></div>
      </div>
    </Panel>
  </div>
}
