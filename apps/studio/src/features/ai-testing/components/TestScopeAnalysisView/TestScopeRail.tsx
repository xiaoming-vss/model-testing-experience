import {
  ApartmentOutlined,
  BranchesOutlined,
  InboxOutlined,
  LockOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useEffect, useId, useRef, type RefObject } from 'react'
import { cx } from '@/shared/utils/cx'
import {
  SCOPE_STATUS,
  questionRelatedCounts,
  type ScopeCategoryKey,
  type ScopeCategoryView,
  type ScopeEntryView,
  type ScopeStatusKey,
} from '../../utils/testScopeAnalysis'
import {
  CLEAR_BUTTON,
  FILTER_BUTTON,
  FILTER_BUTTON_SELECTED,
  FILTER_GRID,
  FILTER_SUMMARY,
  LIST,
  LIST_GROUP_TITLE,
  LIST_ID,
  LIST_ITEM,
  LIST_ITEM_SELECTED,
  LIST_NAME,
  RAIL_BODY,
  RAIL_FOOTER,
  RAIL_PANEL,
  SCOPE_BAR,
  SCOPE_BAR_SEGMENT,
  SCOPE_CELL,
  SCOPE_CELL_ATTENTION,
  SCOPE_CELL_COUNT,
  SCOPE_CELL_LABEL,
  SCOPE_CELL_SELECTED,
  SCOPE_MATRIX,
  SEARCH_INPUT,
  SEARCH_KBD,
  SEARCH_WRAP,
  STATUS_BAR_TONE,
  STATUS_DOT,
  STATUS_DOT_TONE,
  STATUS_PLAIN,
} from './testScopeClasses'

export type ScopeStatusFilter = 'all' | ScopeStatusKey

const CATEGORY_ICONS = {
  testObjects: ApartmentOutlined,
  impactAreas: BranchesOutlined,
  risks: WarningOutlined,
  openQuestions: QuestionCircleOutlined,
}

const STATUS_ORDER = ['confirmed', 'inferred', 'unconfirmed'] as const

function CategoryMatrix({ categories, active, onSelect }: {
  categories: ScopeCategoryView[]
  active: ScopeCategoryKey
  onSelect: (key: ScopeCategoryKey) => void
}) {
  return <div className={SCOPE_MATRIX} role="group" aria-label="测试范围分类">
    {categories.map((category) => {
      const selected = category.key === active
      const Icon = CATEGORY_ICONS[category.key]
      const selectedClass = selected
        ? category.key === 'openQuestions' ? SCOPE_CELL_ATTENTION : SCOPE_CELL_SELECTED
        : ''
      const countClass = cx(
        SCOPE_CELL_COUNT,
        category.key === 'openQuestions' && 'text-app-status-warning-text',
        selected && category.key !== 'openQuestions' && 'text-app-accent',
      )
      const iconClass = selected
        ? category.key === 'openQuestions' ? 'text-app-status-warning-text' : 'text-app-accent'
        : 'text-app-surface-text-muted'
      return <button
        key={category.key}
        type="button"
        className={cx(SCOPE_CELL, selectedClass)}
        aria-pressed={selected}
        aria-label={`${category.label}，${category.items.length} 条${selected ? '，当前分类' : ''}`}
        title={category.hint}
        onClick={() => onSelect(category.key)}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <Icon className={cx('shrink-0 text-[14px]', iconClass)} aria-hidden="true" />
          <span className={SCOPE_CELL_LABEL}>{category.label}</span>
          <span className={countClass}>{category.items.length}</span>
        </span>
        <span className={SCOPE_BAR} aria-hidden="true">
          {STATUS_ORDER.map((status) => {
            const count = category.statusCounts[status]
            return count
              ? <i key={status} className={cx(SCOPE_BAR_SEGMENT, STATUS_BAR_TONE[SCOPE_STATUS[status].tone])} style={{ flexGrow: count }} />
              : null
          })}
        </span>
      </button>
    })}
  </div>
}

function FilterRow({ category, filter, onChange }: {
  category: ScopeCategoryView
  filter: ScopeStatusFilter
  onChange: (value: ScopeStatusFilter) => void
}) {
  const filters: Array<{ key: ScopeStatusFilter; label: string; count: number }> = [
    { key: 'all', label: '全部', count: category.items.length },
    ...STATUS_ORDER.map((status) => ({ key: status, label: SCOPE_STATUS[status].label, count: category.statusCounts[status] })),
  ]
  return <div className={FILTER_GRID} role="group" aria-label="按依据状态筛选">
    {filters.map((item) => {
      const selected = filter === item.key
      const disabled = item.key !== 'all' && item.count === 0
      const meta = item.key === 'all' ? null : SCOPE_STATUS[item.key]
      return <button
        key={item.key}
        type="button"
        className={cx(FILTER_BUTTON, selected && FILTER_BUTTON_SELECTED)}
        aria-pressed={selected}
        disabled={disabled}
        title={disabled ? `暂无${item.label}条目` : `${item.label} ${item.count} 条`}
        onClick={() => onChange(item.key)}
      >
        {meta
          ? <span className={cx(STATUS_DOT, STATUS_DOT_TONE[meta.tone])} aria-hidden="true" />
          : <span className="size-[5px] shrink-0 rounded-full border border-app-surface-text-muted" aria-hidden="true" />}
        <span>{item.label}</span>
        <b className="font-mono text-[10px] font-medium text-app-surface-text-muted">{item.count}</b>
      </button>
    })}
  </div>
}

function QuestionSummary({ category }: { category: ScopeCategoryView }) {
  const related = questionRelatedCounts(category)
  return <div className={FILTER_SUMMARY} role="note" aria-label="待确认项的关联范围">
    <span className={cx(STATUS_DOT, 'bg-app-status-warning-text')} aria-hidden="true" />
    <span>涉及 <b className="font-mono font-semibold text-app-status-warning-text">{related.objects}</b> 个测试对象 · <b className="font-mono font-semibold text-app-status-warning-text">{related.impacts}</b> 个影响范围 · <b className="font-mono font-semibold text-app-status-warning-text">{related.risks}</b> 个风险</span>
  </div>
}

function ScopeItem({ item, selected, onSelect }: {
  item: ScopeEntryView
  selected: boolean
  onSelect: (id: string) => void
}) {
  const meta = SCOPE_STATUS[item.status]
  return <button
    type="button"
    className={cx(LIST_ITEM, selected && LIST_ITEM_SELECTED)}
    aria-current={selected ? 'true' : 'false'}
    title={item.title}
    data-scope-item={item.id}
    onClick={() => onSelect(item.id)}
  >
    <span className={LIST_ID}>{item.id}</span>
    <span className={LIST_NAME}>{item.title}</span>
    <span className={STATUS_PLAIN}>
      <span className={cx(STATUS_DOT, STATUS_DOT_TONE[meta.tone])} aria-hidden="true" />
      {meta.label}
    </span>
  </button>
}

function ScopeList({ category, items, activeId, hasFilters, onSelect, onClear }: {
  category: ScopeCategoryView
  items: ScopeEntryView[]
  activeId?: string
  hasFilters: boolean
  onSelect: (id: string) => void
  onClear: () => void
}) {
  const listRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const activeItem = activeId
      ? [...list.querySelectorAll<HTMLElement>('[data-scope-item]')].find((node) => node.dataset.scopeItem === activeId)
      : undefined
    if (!activeItem) {
      list.scrollTop = 0
      return
    }
    const listBox = list.getBoundingClientRect()
    const itemBox = activeItem.getBoundingClientRect()
    if (itemBox.top < listBox.top) list.scrollTop -= listBox.top - itemBox.top
    else if (itemBox.bottom > listBox.bottom) list.scrollTop += itemBox.bottom - listBox.bottom
  }, [activeId, category.key, items])

  if (!items.length) {
    const Icon = hasFilters ? SearchOutlined : InboxOutlined
    return <nav ref={listRef} className={LIST} aria-label={`${category.label}列表`}>
      <div className="flex flex-col items-center justify-center gap-1.5 px-3 py-8 text-center">
        <Icon className="text-[22px] text-app-surface-text-muted" aria-hidden="true" />
        <strong className="text-[12px] font-semibold text-app-surface-text">{hasFilters ? '没有匹配的条目' : `暂无${category.label}`}</strong>
        <span className="text-[11px] leading-[1.5] text-app-surface-text-muted">{hasFilters ? '换个关键词，或清除状态筛选。' : '当前产物没有这一类内容。'}</span>
        {hasFilters ? <button type="button" className={CLEAR_BUTTON} onClick={onClear}>清除筛选</button> : null}
      </div>
    </nav>
  }

  const visibleIds = new Set(items.map((item) => item.id))
  const groups = category.groups.length
    ? category.groups
      .map((group) => ({ ...group, items: group.items.filter((item) => visibleIds.has(item.id)) }))
      .filter((group) => group.items.length > 0)
    : [{ label: '', items }]

  return <nav ref={listRef} className={LIST} aria-label={`${category.label}列表`}>
    {groups.map((group, index) => <section key={`${group.label || '全部'}-${index}`} aria-label={group.label || category.label}>
      {group.label ? <h3 className={LIST_GROUP_TITLE}>
        <span>{group.label}</span>
        <span className="font-mono text-[10px] font-medium text-app-surface-text-muted">{group.items.length}</span>
      </h3> : null}
      {group.items.map((item) => <ScopeItem key={item.id} item={item} selected={item.id === activeId} onSelect={onSelect} />)}
    </section>)}
  </nav>
}

export function TestScopeRail({ category, categories, items, activeId, query, filter, searchRef, onCategory, onQuery, onFilter, onSelect, onClear }: {
  category: ScopeCategoryView
  categories: ScopeCategoryView[]
  items: ScopeEntryView[]
  activeId?: string
  query: string
  filter: ScopeStatusFilter
  searchRef: RefObject<HTMLInputElement | null>
  onCategory: (key: ScopeCategoryKey) => void
  onQuery: (value: string) => void
  onFilter: (value: ScopeStatusFilter) => void
  onSelect: (id: string) => void
  onClear: () => void
}) {
  const searchId = useId()
  const hasFilters = Boolean(query.trim()) || filter !== 'all'
  const total = category.items.length
  const countLabel = items.length === total ? String(total) : `${items.length}/${total}`
  const pending = category.statusCounts.unconfirmed
  const summary = hasFilters
    ? `共 ${total} 个 · ${items.length} 个匹配`
    : `共 ${total} 个${category.unit}`

  return <aside className={RAIL_PANEL} aria-label="测试范围导航">
    <div className={RAIL_BODY}>
      <div className="flex-none px-0.5">
        <div className="flex items-baseline gap-2">
          <h2 className="m-0 text-[15px] font-semibold tracking-[-0.01em] text-app-surface-text">测试范围</h2>
          <span className="rounded-full border border-app-surface-border bg-app-surface px-1.5 py-0.5 font-mono text-[11px] leading-none text-app-surface-text-muted" title={`当前显示 ${items.length} / ${total}`}>{countLabel}</span>
        </div>
        <p className="mt-1 text-[11px] leading-[1.45] text-app-surface-text-muted">按对象、影响与风险审阅</p>
      </div>

      <CategoryMatrix categories={categories} active={category.key} onSelect={onCategory} />

      <div className="mt-2 flex min-h-[31px] items-start gap-1.5 px-0.5 text-[11px] leading-[1.5] text-app-surface-text-muted">
        <span className={cx('mt-1.5 size-1 shrink-0 rounded-full', category.key === 'openQuestions' ? 'bg-app-status-warning-text' : 'bg-app-accent')} aria-hidden="true" />
        <span>{category.hint}</span>
      </div>

      <div className={SEARCH_WRAP}>
        <SearchOutlined className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[12px] text-app-surface-text-muted" aria-hidden="true" />
        <label className="sr-only" htmlFor={searchId}>搜索当前分类条目</label>
        <input
          ref={searchRef}
          id={searchId}
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={query}
          placeholder="搜索 ID、名称或描述"
          className={SEARCH_INPUT}
          onChange={(event) => onQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return
            if (query) {
              onQuery('')
              event.preventDefault()
            } else {
              event.currentTarget.blur()
            }
          }}
        />
        <kbd className={SEARCH_KBD}>/</kbd>
      </div>

      {category.key === 'openQuestions'
        ? <QuestionSummary category={category} />
        : <FilterRow category={category} filter={filter} onChange={onFilter} />}

      <ScopeList category={category} items={items} activeId={activeId} hasFilters={hasFilters} onSelect={onSelect} onClear={onClear} />
    </div>

    <footer className={RAIL_FOOTER}>
      <span>{summary}</span>
      {pending ? <span className="text-app-status-warning-text">{pending} 待确认</span> : null}
      <span className="ml-auto inline-flex items-center gap-1"><LockOutlined aria-hidden="true" />只读</span>
    </footer>
  </aside>
}
