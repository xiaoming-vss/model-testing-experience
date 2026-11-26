import { ApartmentOutlined, FileTextOutlined, LockOutlined, PlusCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import { CASE_DECISION, MAINTENANCE_DECISIONS, REVIEW_DECISIONS, type CaseVerificationData } from '../../utils/historicalCaseVerificationView'
import { FOOTER_READONLY } from '../HistoricalRelationView/historicalRelationClasses'
import {
  CAT_BAR, CAT_BAR_SEGMENT, CAT_NAME, CAT_NAV, CAT_ROW, CAT_ROW_SELECTED, CAT_TOTAL, FILTER_CHIPS, FILTER_CHIP,
  FILTER_CHIP_SELECTED, FILTER_LABEL, FILTER_ROW, LIST, LIST_ID, LIST_ITEM, LIST_ITEM_SELECTED, LIST_NAME, RAIL_BODY,
  RAIL_FOOTER, RAIL_PANEL, STATUS_DOT,
} from '../TestScopeAnalysisView/testScopeClasses'
import type { VerificationCategory, VerificationFilter, VerificationListItem } from './verificationListing'
import {
  CATEGORY_ICON, CATEGORY_ROW_IDLE, CATEGORY_TEXT_ATTENTION, CATEGORY_TEXT_SELECTED, CAT_ROW_ATTENTION_REVIEW, DOT,
  FILTER_CHIP_IDLE, FILTER_COUNT, LIST_EMPTY,
} from './historicalCaseVerificationClasses'

const CATEGORY_LABELS = { cases: '待维护用例', rules: '规则影响', points: '补测测试点', pending: '待确认' } as const
const CATEGORY_ICONS = { rules: ApartmentOutlined, cases: FileTextOutlined, points: PlusCircleOutlined, pending: QuestionCircleOutlined }

function CategoryNav({ category, data, onSelect }: {
  category: VerificationCategory
  data: CaseVerificationData
  onSelect: (category: VerificationCategory) => void
}) {
  const totals = {
    rules: data.batches.length,
    cases: data.cases.length,
    points: data.points.length,
    pending: data.decisions.needs_confirmation ?? 0,
  }
  return <nav className={CAT_NAV} aria-label="历史用例核验分类">
    {(Object.keys(CATEGORY_LABELS) as VerificationCategory[]).map((key) => {
      const selected = category === key
      const attention = key === 'pending'
      const Icon = CATEGORY_ICONS[key]
      const textClass = attention ? CATEGORY_TEXT_ATTENTION : CATEGORY_TEXT_SELECTED
      return <button
        key={key}
        type="button"
        className={cx(CAT_ROW, selected ? (attention ? CAT_ROW_ATTENTION_REVIEW : CAT_ROW_SELECTED) : CATEGORY_ROW_IDLE)}
        aria-pressed={selected}
        aria-label={`${CATEGORY_LABELS[key]}，${totals[key]} 条${selected ? '，当前分类' : ''}`}
        onClick={() => onSelect(key)}
      >
        <Icon className={cx(CATEGORY_ICON, selected ? textClass : 'text-app-surface-text-muted')} aria-hidden="true" />
        <span className={cx(CAT_NAME, selected ? textClass : 'text-app-surface-text')}>{CATEGORY_LABELS[key]}</span>
        <span className={cx(CAT_TOTAL, selected ? textClass : 'text-app-surface-text')}>{totals[key]}</span>
        <span className={CAT_BAR} aria-hidden="true">
          {(key === 'rules' ? REVIEW_DECISIONS : key === 'cases' ? MAINTENANCE_DECISIONS : [])
            .filter(decision => data.decisions[decision])
            .map(decision => <i key={decision} className={cx(CAT_BAR_SEGMENT, DOT[CASE_DECISION[decision].tone])} style={{ flexGrow: data.decisions[decision] }} />)}
        </span>
      </button>
    })}
  </nav>
}

function FilterRow({ category, data, filter, onChange }: {
  category: VerificationCategory
  data: CaseVerificationData
  filter: VerificationFilter
  onChange: (filter: VerificationFilter) => void
}) {
  // 筛选芯片计数为 0 时禁用；「全部」始终可选。
  const todo = data.batches.filter(batch => batch.findings.length > 0).length
  const options: Array<{ key: VerificationFilter; label: string; count: number }> = category === 'rules'
    ? [
        { key: 'all', label: '全部', count: data.batches.length },
        { key: 'todo', label: '有待办', count: todo },
        { key: 'clear', label: '无待办', count: data.batches.length - todo },
      ]
    : [
        { key: 'all', label: '全部', count: data.cases.length },
        ...MAINTENANCE_DECISIONS.map(key => ({
          key,
          label: CASE_DECISION[key].label,
          count: data.cases.filter(item => item.findings.some(finding => finding.decision.key === key)).length,
        })),
      ]
  const selected = options.find(option => option.key === filter) ?? options[0]
  return <div className={FILTER_ROW}>
    <span className={FILTER_LABEL}>{category === 'rules' ? '处理' : '结论'}</span>
    <div className={FILTER_CHIPS} role="group" aria-label="筛选">
      {options.map((option) => {
        const active = option.key === selected.key
        const disabled = option.key !== 'all' && option.count === 0
        const decision = option.key === 'all' || option.key === 'todo' || option.key === 'clear' ? null : CASE_DECISION[option.key]
        return <button
          key={option.key}
          type="button"
          className={cx(FILTER_CHIP, active ? FILTER_CHIP_SELECTED : FILTER_CHIP_IDLE)}
          aria-pressed={active}
          disabled={disabled}
          title={disabled ? `暂无${option.label}` : `${option.label} ${option.count} 条`}
          onClick={() => onChange(option.key)}
        >
          {decision ? <span className={cx(STATUS_DOT, DOT[decision.tone])} aria-hidden="true" /> : null}
          {option.label}
          <b className={cx(FILTER_COUNT, active ? 'text-app-accent' : 'text-app-surface-text-muted')}>{option.count}</b>
        </button>
      })}
    </div>
  </div>
}

function ListItemRow({ item, selected, onSelect }: { item: VerificationListItem; selected: boolean; onSelect: (id: string) => void }) {
  return <button
    type="button"
    className={cx(LIST_ITEM, selected && LIST_ITEM_SELECTED)}
    aria-current={selected ? 'true' : 'false'}
    title={item.name}
    onClick={() => onSelect(item.id)}
  >
    <span className={LIST_ID}>{item.lead}</span>
    <span className={LIST_NAME}>{item.name}</span>
    {item.status}
  </button>
}

/** 历史用例核验导航：待维护用例、规则影响、补测测试点、待确认。 */
export function HistoricalCaseVerificationRail({ category, data, items, activeId, filter, emptyText, onCategory, onFilter, onSelect }: {
  category: VerificationCategory
  data: CaseVerificationData
  items: VerificationListItem[]
  activeId?: string
  filter: VerificationFilter
  emptyText: string
  onCategory: (category: VerificationCategory) => void
  onFilter: (filter: VerificationFilter) => void
  onSelect: (id: string) => void
}) {
  return <aside className={RAIL_PANEL} aria-label="历史用例核验导航">
    <div className={RAIL_BODY}>
      <CategoryNav category={category} data={data} onSelect={onCategory} />
      {category === 'rules' || category === 'cases' ? <FilterRow category={category} data={data} filter={filter} onChange={onFilter} /> : null}
      {items.length
        ? <nav className={LIST} aria-label={`${CATEGORY_LABELS[category]}列表`}>
          {items.map(item => <ListItemRow key={item.id} item={item} selected={item.id === activeId} onSelect={onSelect} />)}
        </nav>
        : <p className={LIST_EMPTY}>{emptyText}</p>}
    </div>
    <footer className={RAIL_FOOTER}>
      <span>共 {data.batches.length} 条规则</span>
      <span>{data.cases.length} 条待维护用例</span>
      <span className={FOOTER_READONLY}><LockOutlined aria-hidden="true" />只读</span>
    </footer>
  </aside>
}
