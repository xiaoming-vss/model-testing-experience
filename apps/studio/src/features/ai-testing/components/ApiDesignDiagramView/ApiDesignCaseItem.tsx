import { RightOutlined } from '@ant-design/icons'
import { useId } from 'react'
import type { ApiDesignCaseView } from '../../utils/apiDesignDiagram'
import { expectedStatusLabel, patchOpTone, priorityTone, SMALL_SECONDARY_TEXT, statusTone } from './apiDesignClasses'
import styles from '../../styles/api-design.module.css'

const CHIP_BASE = 'inline-flex h-[18px] flex-none items-center rounded-[4px] border px-1.5 font-mono text-[9.5px] font-semibold leading-none'
const OP_BASE = 'inline-flex h-[18px] flex-none items-center rounded-[4px] border px-1.5 text-[9.5px] font-semibold leading-none'
const EVIDENCE_HEAD = 'mb-2 text-[10px] font-semibold tracking-[0.06em] text-[var(--ai-text-muted)]'
const MUTED_LINE = 'm-0 text-[12px] leading-[1.6] text-[var(--ai-text-secondary)]'

function statusTextTone(statusClass: string) {
  if (statusClass === '2xx') return 'text-[var(--app-result-success-text)]'
  if (statusClass === '4xx') return 'text-[var(--app-request-error-text)]'
  if (statusClass === '5xx') return 'text-[var(--app-status-warning-text)]'
  return 'text-[var(--ai-text-secondary)]'
}

function CasePatches({ apiCase }: { apiCase: ApiDesignCaseView }) {
  if (!apiCase.patchOps.length) return <p className={MUTED_LINE}>无参数变异，沿用提取基线请求</p>
  return <ul className="m-0 flex list-none flex-col gap-1 p-0">
    {apiCase.patchOps.map(patch => <li className="flex flex-wrap items-baseline gap-1.5 py-1 text-[11.5px]" key={patch.key}>
      <span className={`${OP_BASE} ${patchOpTone(patch.op)}`}>{patch.opLabel}</span>
      <code className="text-[11.5px] text-[var(--ai-text)] [overflow-wrap:anywhere]">{patch.target}</code>
      {patch.valueLabel ? <>
        <span className="font-mono text-[11px] text-[var(--ai-text-muted)]">=</span>
        <code className="text-[11.5px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]">{patch.valueLabel}</code>
      </> : null}
    </li>)}
  </ul>
}

function CaseAssertions({ apiCase }: { apiCase: ApiDesignCaseView }) {
  if (!apiCase.assertions.length) {
    return <p className={MUTED_LINE}>{apiCase.statusClass === '4xx' ? '仅校验状态区间' : '无额外业务断言'}</p>
  }
  return <div>
    {apiCase.assertions.map(assertion => <div className="flex flex-wrap items-baseline gap-1.5 border-t border-[var(--app-frame-divider-soft)] py-1 text-[11.5px] first:border-t-0" key={assertion.key}>
      <span className="min-w-[52px] flex-none text-[9.5px] font-semibold tracking-[0.03em] text-[var(--ai-text-muted)]">{assertion.sourceLabel}</span>
      <code className="text-[11.5px] text-[var(--ai-text)] [overflow-wrap:anywhere]">{assertion.target}</code>
      {assertion.comparatorLabel ? <span className={SMALL_SECONDARY_TEXT}>{assertion.comparatorLabel}</span> : null}
      {assertion.hasExpected ? <code className="text-[11.5px] text-[var(--app-accent)] [overflow-wrap:anywhere]">{assertion.expected}</code> : null}
    </div>)}
  </div>
}

function CaseExpected({ apiCase }: { apiCase: ApiDesignCaseView }) {
  return <>
    <div className={`flex items-center gap-1.5 pb-2 ${statusTextTone(apiCase.statusClass)}`}>
      <span className="h-1.5 w-1.5 flex-none rounded-full bg-current" aria-hidden />
      <span className="font-mono text-[11.5px] font-semibold">HTTP {apiCase.statusClass || '—'}</span>
      <span className={SMALL_SECONDARY_TEXT}>{expectedStatusLabel(apiCase.statusClass)}</span>
    </div>
    <CaseAssertions apiCase={apiCase} />
  </>
}

export function ApiDesignCaseItem({ apiCase, expanded, onToggle }: {
  apiCase: ApiDesignCaseView
  expanded: boolean
  onToggle: () => void
}) {
  const bodyId = useId()
  return <article className="border-t border-[var(--app-frame-divider-soft)] first:border-t-0">
    <button type="button" className="group flex w-full items-center gap-2.5 rounded-[6px] border-0 bg-transparent px-0.5 py-2.5 text-left text-inherit focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]"
      aria-expanded={expanded} aria-controls={bodyId} onClick={onToggle}
      aria-label={`${apiCase.priority ? `${apiCase.priority} ` : ''}${apiCase.title}${apiCase.statusClass ? ` ${apiCase.statusClass}` : ''}`}>
      <span className={`${styles.chevron}${expanded ? ` ${styles.chevronOpen}` : ''} inline-flex flex-none text-[10px] text-[var(--ai-text-muted)]`} aria-hidden>
        <RightOutlined />
      </span>
      {apiCase.priority ? <span className={`${CHIP_BASE} ${priorityTone(apiCase.priority)}`}>{apiCase.priority}</span> : null}
      <span className="min-w-0 flex-1 text-[13.5px] font-medium leading-[1.5] text-[var(--ai-text)] [overflow-wrap:anywhere] group-hover:text-[var(--ai-accent)]">{apiCase.title}</span>
      <span className={`${CHIP_BASE} ${statusTone(apiCase.statusClass)}`}>{apiCase.statusClass || '—'}</span>
    </button>
    <div id={bodyId} aria-hidden={!expanded} className={`${styles.caseBody}${expanded ? ` ${styles.caseBodyOpen}` : ''}`}>
      <div className={styles.caseBodyInner}>
        <div className="pb-4 pl-6 pr-1">
          {apiCase.intent ? <p className="m-0 mb-3.5 max-w-[74ch] text-[13px] leading-[1.7] text-[var(--ai-text-secondary)]">{apiCase.intent}</p> : null}
          <div className="grid grid-cols-2 border-y border-[var(--app-frame-divider-soft)] max-narrow:grid-cols-1">
            <section className="min-w-0 py-3 pr-5">
              <h4 className={EVIDENCE_HEAD}>请求变更</h4>
              <CasePatches apiCase={apiCase} />
            </section>
            <section className="min-w-0 border-l border-[var(--app-frame-divider-soft)] py-3 pl-5 max-narrow:border-l-0 max-narrow:border-t max-narrow:pl-0 max-narrow:pt-3">
              <h4 className={EVIDENCE_HEAD}>预期结果</h4>
              <CaseExpected apiCase={apiCase} />
            </section>
          </div>
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="text-[10px] tracking-[0.04em] text-[var(--ai-text-muted)]">设计依据</span>
              <code className="rounded-[4px] border border-[var(--app-surface-border)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[10.5px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]">{apiCase.basisLabel}</code>
            </div>
            {apiCase.id ? <span className="max-w-[45%] truncate font-mono text-[10px] text-[var(--ai-text-muted)] max-narrow:hidden" title={apiCase.id}>#{apiCase.id}</span> : null}
          </div>
        </div>
      </div>
    </div>
  </article>
}
