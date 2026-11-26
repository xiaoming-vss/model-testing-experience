import { cx } from '@/shared/utils/cx'
import type { RuleScope } from '../../utils/historicalRelationView'
import {
  COMPARE,
  COMPARE_CURRENT,
  COMPARE_HEAD,
  COMPARE_HEAD_CURRENT,
  COMPARE_PREVIOUS,
  COMPARE_TEXT,
  SCOPE_CELL,
  SCOPE_LABEL,
  SCOPE_STRIP,
  SCOPE_VALUE,
} from './historicalRelationClasses'

function ScopeCell({ label, values }: { label: string; values: string[] }) {
  return <div className={SCOPE_CELL}>
    <dt className={SCOPE_LABEL}>{label}</dt>
    <dd className={SCOPE_VALUE}>{values.length ? values.join('、') : '未列明'}</dd>
  </div>
}

/** 规则对照：历史规则与本次规则并排，后接适用范围。历史需求关联与历史用例核验共用同一份。 */
export function RuleCompare({ rule }: { rule: { previousRule: string; currentRule: string | null; scope: RuleScope } }) {
  const retired = rule.currentRule === null
  return <>
    <div className={COMPARE}>
      <div className={COMPARE_PREVIOUS}>
        <h3 className={COMPARE_HEAD}>历史规则</h3>
        <p className={COMPARE_TEXT}>{rule.previousRule}</p>
      </div>
      <div className={COMPARE_CURRENT}>
        <h3 className={COMPARE_HEAD_CURRENT}>{retired ? '本次规则（已取消）' : '本次规则'}</h3>
        <p className={cx(COMPARE_TEXT, retired && 'text-app-surface-text-muted')}>
          {retired ? '没有接续规则' : rule.currentRule}
        </p>
      </div>
    </div>
    <dl className={SCOPE_STRIP}>
      <ScopeCell label="角色" values={rule.scope.roles} />
      <ScopeCell label="状态" values={rule.scope.states} />
      <ScopeCell label="条件" values={rule.scope.conditions} />
    </dl>
  </>
}
