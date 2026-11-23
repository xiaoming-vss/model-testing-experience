import type { ApiConfigRule } from '../../utils/apiConfigDiagram'
import { GROUP_COUNT, RULE_GRID, RULE_HEAD, RULE_ROW, SMALL_SECONDARY_TEXT, STRONG_TEXT } from './apiConfigClasses'

function RuleColumn({ title, rules, emptyText }: { title: string; rules: ApiConfigRule[]; emptyText: string }) {
  return <section className="min-w-0" aria-label={title}>
    <header className={RULE_HEAD}>
      <h3 className="m-0 text-[12px] font-semibold text-[var(--ai-text)]">{title}</h3>
      <span className={GROUP_COUNT}>{rules.length}</span>
    </header>
    {rules.length ? <div>{rules.map((rule, index) => <div key={`${rule.name}-${index}`} className={RULE_ROW}>
      <strong className={`${STRONG_TEXT} text-[12px] [overflow-wrap:anywhere]`}>{rule.name}</strong>
      {rule.detail ? <span className={`${SMALL_SECONDARY_TEXT} [overflow-wrap:anywhere]`}>{rule.detail}</span> : null}
    </div>)}</div> : <p className={`m-0 py-2 ${SMALL_SECONDARY_TEXT}`}>{emptyText}</p>}
  </section>
}

export function ApiConfigRuleSection({ extractRules, assertRules }: { extractRules: ApiConfigRule[]; assertRules: ApiConfigRule[] }) {
  return <div className={RULE_GRID}>
    <RuleColumn title="提取规则" rules={extractRules} emptyText="暂无提取规则" />
    <RuleColumn title="断言规则" rules={assertRules} emptyText="暂无断言规则" />
  </div>
}
