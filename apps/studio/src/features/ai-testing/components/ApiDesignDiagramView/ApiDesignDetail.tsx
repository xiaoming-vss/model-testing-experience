import { CheckCircleOutlined, CopyOutlined, WarningOutlined } from '@ant-design/icons'
import { useId, type RefObject } from 'react'
import type { ApiDesignInterfaceView } from '../../utils/apiDesignDiagram'
import { ApiDesignCaseItem } from './ApiDesignCaseItem'
import { ACCENT_FILTER_ACTIVE, CATEGORY_DESCRIPTIONS, CATEGORY_ORDER, categoryMeta, FILTER_BASE, METHOD_BASE, methodTone, NEUTRAL_FILTER_IDLE, SMALL_SECONDARY_TEXT, STRONG_TEXT } from './apiDesignClasses'

export function ApiDesignDetail({ view, filter, expanded, onFilter, onToggleCase, onToggleAll, onCopyPath, uncoveredRef }: {
  view: ApiDesignInterfaceView
  filter: string
  expanded: Set<string>
  onFilter: (filter: string) => void
  onToggleCase: (key: string) => void
  onToggleAll: () => void
  onCopyPath: () => void
  uncoveredRef: RefObject<HTMLElement | null>
}) {
  const titleId = useId()
  const uncoveredTitleId = useId()
  const categories = [...CATEGORY_ORDER, ...Object.keys(view.categoryCounts).filter(category => !CATEGORY_ORDER.includes(category))]
  const visibleCases = view.cases.filter(item => filter === 'all' || item.category === filter)
  const allExpanded = visibleCases.length > 0 && visibleCases.every(item => expanded.has(item.key))
  const shownCategories = categories.filter(category => (filter === 'all' || category === filter) && view.cases.some(item => item.category === category))

  return <section aria-labelledby={titleId} className="min-w-0">
    <header className="border-b border-[var(--app-frame-divider-soft)] pb-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className={`${METHOD_BASE} ${methodTone(view.method)}`}>{view.method}</span>
        <h2 id={titleId} className="m-0 min-w-0 text-[18px] font-semibold leading-tight text-[var(--ai-text)] [overflow-wrap:anywhere]">{view.name}</h2>
        <button type="button" aria-label="复制接口路径" title="复制接口路径" onClick={onCopyPath}
          className="inline-flex h-7 w-7 flex-none items-center justify-center rounded-[6px] border-0 bg-transparent text-[var(--ai-text-muted)] hover:bg-[var(--app-surface-hover)] hover:text-[var(--ai-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]">
          <CopyOutlined aria-hidden />
        </button>
      </div>
      <div className="mt-2">
        <code className="inline-block max-w-full rounded-[6px] border border-[var(--app-surface-border)] bg-[var(--app-glass-surface-68)] px-2 py-1 font-mono text-[11.5px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]">{view.path}</code>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-2.5 text-[11.5px] text-[var(--ai-text-secondary)]">
        <span><b className={STRONG_TEXT}>{view.cases.length}</b> 条用例</span>
        <span className="h-3 w-px bg-[var(--app-surface-border)]" aria-hidden />
        {view.uncovered.length
          ? <span className="inline-flex items-center gap-1 text-[var(--app-status-warning-text)]"><WarningOutlined aria-hidden />{view.uncovered.length} 条约束未覆盖</span>
          : <span className="inline-flex items-center gap-1 text-[var(--app-result-success-text)]"><CheckCircleOutlined aria-hidden />约束全覆盖</span>}
      </div>
    </header>

    <div className="sticky top-0 z-[1] flex flex-wrap items-center justify-between gap-2.5 border-b border-[var(--app-frame-divider-soft)] bg-[var(--ai-popover-surface)] py-2">
      <div role="group" aria-label="按分类筛选用例" className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={`${FILTER_BASE} ${filter === 'all' ? ACCENT_FILTER_ACTIVE : NEUTRAL_FILTER_IDLE}`}
          aria-label={`全部，${view.cases.length} 条用例`} aria-pressed={filter === 'all'} onClick={() => onFilter('all')}>
          全部<span className="font-mono text-[10px]">{view.cases.length}</span>
        </button>
        {categories.map(category => {
          const count = view.categoryCounts[category] ?? 0
          const meta = categoryMeta(category)
          return <button type="button" key={category} className={`${FILTER_BASE} ${filter === category ? meta.active : NEUTRAL_FILTER_IDLE}`}
            aria-label={`${meta.label}，${count} 条用例`} aria-pressed={filter === category} disabled={count === 0} onClick={() => onFilter(category)}>
            <i className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
            {meta.label}<span className="font-mono text-[10px]">{count}</span>
          </button>
        })}
      </div>
      <button type="button" className="flex-none border-0 bg-transparent p-0 text-[11.5px] text-[var(--ai-text-secondary)] hover:text-[var(--ai-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]" onClick={onToggleAll}>
        {allExpanded ? '收起全部' : '展开全部'}
      </button>
    </div>

    <div className="pt-1">
      {shownCategories.map(category => {
        const cases = view.cases.filter(item => item.category === category)
        const meta = categoryMeta(category)
        return <section key={category} className="border-b border-[var(--app-frame-divider-soft)]">
          <header className="flex items-baseline gap-2 pb-1.5 pt-4">
            <h3 className="m-0 flex items-center gap-1.5 text-[12px] font-semibold text-[var(--ai-text-secondary)]">
              <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
              {meta.label}
              <span className="inline-flex min-w-[16px] items-center justify-center rounded-full border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[9.5px] font-normal text-[var(--ai-text-secondary)]">{cases.length}</span>
            </h3>
            {CATEGORY_DESCRIPTIONS[category] ? <span className="text-[11px] text-[var(--ai-text-muted)] max-narrow:hidden">{CATEGORY_DESCRIPTIONS[category]}</span> : null}
          </header>
          <div>{cases.map(item => <ApiDesignCaseItem key={item.key} apiCase={item} expanded={expanded.has(item.key)} onToggle={() => onToggleCase(item.key)} />)}</div>
        </section>
      })}
    </div>

    {view.uncovered.length ? <section ref={uncoveredRef} aria-labelledby={uncoveredTitleId}
      className="mt-7 overflow-hidden rounded-[9px] border border-[var(--app-surface-border)] bg-[var(--app-surface)]">
      <header className="flex flex-col gap-1 border-b border-[var(--app-surface-border)] px-4 py-3">
        <div className="flex items-center gap-2 text-[var(--app-status-warning-text)]">
          <WarningOutlined aria-hidden />
          <h3 id={uncoveredTitleId} className="m-0 text-[12px] font-semibold text-[var(--ai-text)]">未覆盖约束</h3>
          <span className="inline-flex min-w-[17px] items-center justify-center rounded-full border border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] px-1.5 font-mono text-[9.5px] text-[var(--app-status-warning-text)]">{view.uncovered.length}</span>
        </div>
        <p className="m-0 max-w-[48ch] text-[11px] leading-[1.6] text-[var(--ai-text-secondary)]">这些约束没有生成对应用例，可结合风险决定是否补充。</p>
      </header>
      <div>
        {view.uncovered.map(row => <div key={row.key} className="grid grid-cols-[50px_minmax(0,1fr)_auto] items-center gap-3 border-t border-[var(--app-frame-divider-soft)] px-4 py-2.5 first:border-t-0 max-narrow:grid-cols-[minmax(0,1fr)_auto]">
          <span className="justify-self-start rounded-[4px] border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 text-[9.5px] leading-4 text-[var(--ai-text-secondary)] max-narrow:hidden">{row.kindLabel}</span>
          <div className="flex min-w-0 flex-wrap items-baseline gap-2">
            <code className="font-mono text-[11.5px] text-[var(--ai-text)] [overflow-wrap:anywhere]">{row.fieldLabel || '—'}</code>
            {row.constraint ? <span className={SMALL_SECONDARY_TEXT}>{row.constraint}</span> : null}
          </div>
          <span className="whitespace-nowrap rounded-full border border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] px-1.5 text-[9.5px] leading-[17px] text-[var(--app-status-warning-text)]" title={row.reasonDescription}>{row.reasonLabel}</span>
        </div>)}
      </div>
    </section> : <div className="mt-6 flex items-center gap-1.5 border-t border-[var(--app-frame-divider-soft)] pt-3 text-[11.5px] text-[var(--app-result-success-text)]">
      <CheckCircleOutlined aria-hidden />本接口的提取约束均已覆盖
    </div>}
  </section>
}
