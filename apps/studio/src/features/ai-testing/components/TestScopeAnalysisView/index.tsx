import { useEffect, useMemo, useRef, useState } from 'react'
import { notify } from '@/shared/utils/toast'
import { cx } from '@/shared/utils/cx'
import {
  SCOPE_CATEGORIES,
  buildTestScopeView,
  type ScopeCategoryKey,
} from '../../utils/testScopeAnalysis'
import { TestScopeDetail } from './TestScopeDetail'
import { TestScopeRail, type ScopeStatusFilter } from './TestScopeRail'
import { DETAIL_INNER, DETAIL_SCROLL } from './testScopeClasses'

function isNarrow() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(max-width: 900px)').matches
}

function prefersReducedMotion() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function TestScopeAnalysisView({ analysis, materialContent }: {
  analysis: Record<string, unknown>
  materialContent?: string
}) {
  const view = useMemo(() => buildTestScopeView(analysis, materialContent), [analysis, materialContent])
  const categories = useMemo(() => SCOPE_CATEGORIES.map((category) => view.categories[category.key]), [view])
  const [categoryKey, setCategoryKey] = useState<ScopeCategoryKey>('testObjects')
  const [filter, setFilter] = useState<ScopeStatusFilter>('all')
  const [selectedIds, setSelectedIds] = useState<Partial<Record<ScopeCategoryKey, string>>>({})
  const detailRef = useRef<HTMLDivElement>(null)
  const scrollOnSelectionRef = useRef(false)

  const category = view.categories[categoryKey]
  const visibleItems = useMemo(() => category.items.filter((item) => (
    categoryKey === 'openQuestions' || filter === 'all' || item.status === filter
  )), [category, categoryKey, filter])
  const activeId = selectedIds[categoryKey]
  const activeItem = visibleItems.find((item) => item.id === activeId) ?? visibleItems[0]

  useEffect(() => {
    setFilter('all')
    setSelectedIds({})
  }, [view])

  useEffect(() => {
    const detail = detailRef.current
    if (!detail) return
    if (isNarrow()) {
      if (scrollOnSelectionRef.current) {
        detail.scrollIntoView?.({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
      }
    } else {
      detail.scrollTop = 0
    }
    scrollOnSelectionRef.current = false
  }, [activeItem?.id, categoryKey])

  const selectCategory = (key: ScopeCategoryKey) => {
    setCategoryKey(key)
    setFilter('all')
  }

  const selectEntry = (id: string) => {
    setSelectedIds((current) => ({ ...current, [categoryKey]: id }))
    scrollOnSelectionRef.current = true
  }

  const jumpTo = (targetCategory: ScopeCategoryKey, id: string) => {
    setCategoryKey(targetCategory)
    setFilter('all')
    setSelectedIds((current) => ({ ...current, [targetCategory]: id }))
    scrollOnSelectionRef.current = true
  }

  const copyId = (id: string) => {
    if (!navigator.clipboard) {
      notify.error('复制失败，请手动选择 ID')
      return
    }
    void navigator.clipboard.writeText(id)
      .then(() => notify.success('ID 已复制'))
      .catch(() => notify.error('复制失败，请手动选择 ID'))
  }

  return <div className={cx('testScopeRoot flex h-full min-h-0 overflow-hidden bg-app-surface text-app-surface-text max-narrow:flex-col max-narrow:overflow-y-auto')}>
    <TestScopeRail
      category={category}
      categories={categories}
      items={visibleItems}
      activeId={activeItem?.id}
      filter={filter}
      onCategory={selectCategory}
      onFilter={setFilter}
      onSelect={selectEntry}
    />
    <div ref={detailRef} className={cx(DETAIL_SCROLL, 'scroll-mt-2')}>
      <div className={DETAIL_INNER}>
        <TestScopeDetail
          key={`${categoryKey}:${activeItem?.id ?? 'empty'}`}
          category={category}
          entry={activeItem}
          view={view}
          onJump={jumpTo}
          onCopy={copyId}
        />
      </div>
    </div>
  </div>
}
