import { toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { CASE_DECISION } from '../utils/historicalCaseVerificationView'

const decisions = ['modify', 'invalidate', 'reuse'] as const

export function GeneratedCaseHistory({ findings }: { findings: Record<string, unknown>[] }) {
  if (!findings.length) return null

  return <section className="mb-3 border-b border-app-surface-border px-2 pb-2 text-app-surface-text" aria-label="历史用例结论">
    <h2 className="my-2 text-xs font-semibold">历史用例结论</h2>
    {decisions.map(decision => {
      const items = findings.filter(item => item.decision === decision)
      if (!items.length) return null
      return <details key={decision} className="py-1 text-xs">
        <summary className="cursor-pointer rounded px-1 py-1 hover:bg-app-surface-hover">
          <span className="font-medium">{CASE_DECISION[decision].label}</span>
          <span className="ml-2 text-app-surface-text-muted">{items.length}</span>
        </summary>
        <ul className="m-0 list-none divide-y divide-app-surface-border p-0">
          {items.map(item => {
            const caseId = toDisplayText(item.caseId)
            const pointIds = toRecordArray(item.pointRefs).map(point => toDisplayText(point.pointId)).filter(Boolean)
            const modification = toDisplayText(item.modificationHint)
            return <li className="px-1 py-2" key={`${caseId}-${String(item.batchId)}`}>
              <div className="font-medium">{toDisplayText(item.title) || caseId}</div>
              <div className="break-all text-app-surface-text-muted">原用例 ID {caseId}</div>
              <p className="my-1">{toDisplayText(item.reason)}</p>
              {modification ? <p className="my-1">{modification}</p> : null}
              {pointIds.length ? <div className="break-words text-app-surface-text-muted">关联测试点 {pointIds.join('、')}</div> : null}
            </li>
          })}
        </ul>
      </details>
    })}
  </section>
}
