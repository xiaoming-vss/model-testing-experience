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

function isEditableTarget(target: EventTarget | null) {
  return target instanceof HTMLElement
    && (target.matches('input, textarea, select') || target.isContentEditable)
}

export function TestScopeAnalysisView({ analysis, materialContent }: {
  analysis: Record<string, unknown>
  materialContent?: string
}) {
  const view = useMemo(() => buildTestScopeView(analysis, materialContent), [analysis, materialContent])
  const categories = useMemo(() => SCOPE_CATEGORIES.map((category) => view.categories[category.key]), [view])
  const [categoryKey, setCategoryKey] = useState<ScopeCategoryKey>('testObjects')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ScopeStatusFilter>('all')
  const [selectedIds, setSelectedIds] = useState<Partial<Record<ScopeCategoryKey, string>>>({})
  const searchRef = useRef<HTMLInputElement>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const scrollOnSelectionRef = useRef(false)

  const category = view.categories[categoryKey]
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return category.items.filter((item) => {
      if (categoryKey !== 'openQuestions' && filter !== 'all' && item.status !== filter) return false
      if (!normalizedQuery) return true
      return `${item.id} ${item.title} ${item.type} ${item.narrative}`.toLowerCase().includes(normalizedQuery)
    })
  }, [category, categoryKey, filter, query])
  const activeId = selectedIds[categoryKey]
  const activeItem = visibleItems.find((item) => item.id === activeId) ?? visibleItems[0]
  const hasFilters = Boolean(query.trim()) || filter !== 'all'

  useEffect(() => {
    setQuery('')
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

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || isEditableTarget(event.target)) return
      event.preventDefault()
      searchRef.current?.focus()
      searchRef.current?.select()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const selectCategory = (key: ScopeCategoryKey) => {
    setCategoryKey(key)
    setQuery('')
    setFilter('all')
  }

  const selectFilter = (value: ScopeStatusFilter) => {
    setFilter(value)
  }

  const selectEntry = (id: string) => {
    setSelectedIds((current) => ({ ...current, [categoryKey]: id }))
    scrollOnSelectionRef.current = true
  }

  const jumpTo = (targetCategory: ScopeCategoryKey, id: string) => {
    setCategoryKey(targetCategory)
    setQuery('')
    setFilter('all')
    setSelectedIds((current) => ({ ...current, [targetCategory]: id }))
    scrollOnSelectionRef.current = true
  }

  const clearFilters = () => {
    setQuery('')
    setFilter('all')
    searchRef.current?.focus()
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
      query={query}
      filter={filter}
      searchRef={searchRef}
      onCategory={selectCategory}
      onQuery={setQuery}
      onFilter={selectFilter}
      onSelect={selectEntry}
      onClear={clearFilters}
    />
    <div ref={detailRef} className={cx(DETAIL_SCROLL, 'scroll-mt-2')}>
      <div className={DETAIL_INNER}>
        <TestScopeDetail
          key={`${categoryKey}:${activeItem?.id ?? 'empty'}`}
          category={category}
          entry={activeItem}
          view={view}
          hasFilters={hasFilters}
          onJump={jumpTo}
          onCopy={copyId}
          onClear={clearFilters}
        />
      </div>
    </div>
  </div>
}
