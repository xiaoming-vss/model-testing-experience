import { LockOutlined, QuestionCircleOutlined, SwapOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import {
  RELATION_TYPE,
  REVIEW_STATUS,
  RULE_EFFECT,
  RULE_EFFECT_ORDER,
  type HistoricalRelationData,
  type HistoricalRelationView,
  type HistoricalQuestionView,
  type HistoricalTone,
} from '../../utils/historicalRelationView'
import {
  CAT_BAR,
  CAT_BAR_SEGMENT,
  CAT_NAME,
  CAT_NAV,
  CAT_ROW,
  CAT_ROW_ATTENTION,
  CAT_ROW_SELECTED,
  CAT_TOTAL,
  FILTER_CHIPS,
  FILTER_CHIP,
  FILTER_CHIP_SELECTED,
  FILTER_LABEL,
  FILTER_ROW,
  LIST,
  LIST_ID,
  LIST_ITEM,
  LIST_ITEM_SELECTED,
  LIST_NAME,
  RAIL_BODY,
  RAIL_FOOTER,
  RAIL_PANEL,
  STATUS_DOT,
  STATUS_PLAIN,
} from '../TestScopeAnalysisView/testScopeClasses'
import {
  CATEGORY_ICON,
  CATEGORY_ROW_IDLE,
  CATEGORY_TEXT_ATTENTION,
  CATEGORY_TEXT_SELECTED,
  FILTER_CHIP_IDLE,
  FILTER_COUNT,
  FOOTER_READONLY,
  LIST_EMPTY,
  TONE_COLOR,
} from './historicalRelationClasses'

export type HistoricalRelationCategory = 'relations' | 'questions'
export type HistoricalRelationFilter = 'all' | 'linked' | 'unlinked' | keyof typeof RELATION_TYPE
type ListItem = HistoricalRelationView | HistoricalQuestionView
type FilterOption = { key: HistoricalRelationFilter; label: string; count: number; tone?: HistoricalTone }

const LABELS = { relations: '关联需求', questions: '待确认' } as const
const CATEGORY_ICONS = { relations: SwapOutlined, questions: QuestionCircleOutlined }

function CategoryNav({ category, data, onSelect }: {
  category: HistoricalRelationCategory
  data: HistoricalRelationData
  onSelect: (category: HistoricalRelationCategory) => void
}) {
  const linked = data.questions.filter((question) => question.impact).length
  const bars: Record<HistoricalRelationCategory, Array<{ key: string; tone: HistoricalTone | null; count: number }>> = {
    relations: RULE_EFFECT_ORDER.map((effect) => ({
      key: effect,
      tone: RULE_EFFECT[effect].tone,
      count: data.impacts.filter((impact) => impact.effect.key === effect).length,
    })),
    // 未定位到规则的问题没有语义色，用中性色表示。
    questions: [
      { key: 'linked', tone: 'warn', count: linked },
      { key: 'unlinked', tone: null, count: data.questions.length - linked },
    ],
  }
  const totals = { relations: data.relations.length, questions: data.questions.length }
  return <nav className={CAT_NAV} aria-label="历史需求关联分类">
    {(Object.keys(LABELS) as HistoricalRelationCategory[]).map((key) => {
      const selected = category === key
      const attention = key === 'questions'
      const Icon = CATEGORY_ICONS[key]
      const textClass = attention ? CATEGORY_TEXT_ATTENTION : CATEGORY_TEXT_SELECTED
      return <button
        key={key}
        type="button"
        className={cx(CAT_ROW, selected ? (attention ? CAT_ROW_ATTENTION : CAT_ROW_SELECTED) : CATEGORY_ROW_IDLE)}
        aria-pressed={selected}
        aria-label={`${LABELS[key]}，${totals[key]} 条${selected ? '，当前分类' : ''}`}
        onClick={() => onSelect(key)}
      >
        <Icon className={cx(CATEGORY_ICON, selected ? textClass : 'text-app-surface-text-muted')} aria-hidden="true" />
        <span className={cx(CAT_NAME, selected ? textClass : 'text-app-surface-text')}>{LABELS[key]}</span>
        <span className={cx(CAT_TOTAL, selected ? textClass : 'text-app-surface-text')}>{totals[key]}</span>
        <span className={CAT_BAR} aria-hidden="true">
          {bars[key].filter((bar) => bar.count).map((bar) => (
            <i
              key={bar.key}
              className={cx(CAT_BAR_SEGMENT, bar.tone ? TONE_COLOR[bar.tone] : 'bg-app-surface-border')}
              style={{ flexGrow: bar.count }}
            />
          ))}
        </span>
      </button>
    })}
  </nav>
}

function FilterRow({ category, data, filter, onChange }: {
  category: HistoricalRelationCategory
  data: HistoricalRelationData
  filter: HistoricalRelationFilter
  onChange: (filter: HistoricalRelationFilter) => void
}) {
  const linked = data.questions.filter((question) => question.impact).length
  const options: FilterOption[] = category === 'relations'
    ? [
        { key: 'all', label: '全部', count: data.relations.length },
        ...(Object.keys(RELATION_TYPE) as Array<keyof typeof RELATION_TYPE>).map((key) => ({
          key,
          label: RELATION_TYPE[key].label,
          tone: RELATION_TYPE[key].tone,
          count: data.relations.filter((relation) => relation.type.key === key).length,
        })),
      ]
    : [
        { key: 'all', label: '全部', count: data.questions.length },
        { key: 'linked', label: '已定位到规则', count: linked, tone: 'warn' },
        { key: 'unlinked', label: '未定位', count: data.questions.length - linked },
      ]
  const selected = options.find((option) => option.key === filter) ?? options[0]
  return <div className={FILTER_ROW}>
    <span className={FILTER_LABEL}>{category === 'relations' ? '关联类型' : '定位'}</span>
    <div className={FILTER_CHIPS} role="group" aria-label="筛选">
      {options.map((option) => {
        const active = option.key === selected.key
        const disabled = option.key !== 'all' && option.count === 0
        return <button
          key={option.key}
          type="button"
          className={cx(FILTER_CHIP, active ? FILTER_CHIP_SELECTED : FILTER_CHIP_IDLE)}
          aria-pressed={active}
          disabled={disabled}
          title={disabled ? `暂无${option.label}` : `${option.label} ${option.count} 条`}
          onClick={() => onChange(option.key)}
        >
          {option.tone ? <span className={cx(STATUS_DOT, TONE_COLOR[option.tone])} aria-hidden="true" /> : null}
          {option.label}
          <b className={cx(FILTER_COUNT, active ? 'text-app-accent' : 'text-app-surface-text-muted')}>{option.count}</b>
        </button>
      })}
    </div>
  </div>
}

function ListItemRow({ item, selected, onSelect }: { item: ListItem; selected: boolean; onSelect: (id: string) => void }) {
  const isRelation = 'impacts' in item
  const title = isRelation ? item.name : item.question
  return <button
    type="button"
    className={cx(LIST_ITEM, selected && LIST_ITEM_SELECTED)}
    aria-current={selected ? 'true' : 'false'}
    title={title}
    onClick={() => onSelect(item.id)}
  >
    <span className={LIST_ID}>{isRelation ? `${item.impacts.length} 项` : item.id}</span>
    <span className={LIST_NAME}>{title}</span>
    <span className={STATUS_PLAIN}>
      <span className={cx(STATUS_DOT, TONE_COLOR[isRelation ? item.type.tone : 'warn'])} aria-hidden="true" />
      {isRelation ? item.type.label : REVIEW_STATUS.needs_confirmation.label}
    </span>
  </button>
}

/** 历史需求关联导航：关联需求与待确认两个分类，各自带筛选和列表。 */
export function HistoricalRelationRail({ category, data, items, activeId, filter, emptyText, onCategory, onFilter, onSelect }: {
  category: HistoricalRelationCategory
  data: HistoricalRelationData
  items: ListItem[]
  activeId?: string
  filter: HistoricalRelationFilter
  emptyText: string
  onCategory: (category: HistoricalRelationCategory) => void
  onFilter: (filter: HistoricalRelationFilter) => void
  onSelect: (id: string) => void
}) {
  const pending = data.questions.length
  return <aside className={RAIL_PANEL} aria-label="历史需求关联导航">
    <div className={RAIL_BODY}>
      <CategoryNav category={category} data={data} onSelect={onCategory} />
      <FilterRow category={category} data={data} filter={filter} onChange={onFilter} />
      {items.length
        ? <nav className={LIST} aria-label={`${LABELS[category]}列表`}>
          {items.map((item) => (
            <ListItemRow key={item.id} item={item} selected={item.id === activeId} onSelect={onSelect} />
          ))}
        </nav>
        : <p className={LIST_EMPTY}>{emptyText}</p>}
    </div>
    <footer className={RAIL_FOOTER}>
      <span>共 {data.relations.length} 条关联</span>
      {pending ? <span className="text-app-status-warning-text">{pending} 待确认</span> : null}
      <span className={FOOTER_READONLY}><LockOutlined aria-hidden="true" />只读</span>
    </footer>
  </aside>
}
