import { ArrowRightOutlined, CopyOutlined, LockOutlined, WarningOutlined } from '@ant-design/icons'
import { Empty } from 'antd'
import { cx } from '@/shared/utils/cx'
import {
  SCOPE_STATUS,
  relationRows,
  type ScopeCategoryKey,
  type ScopeCategoryView,
  type ScopeEntryView,
  type TestScopeView,
} from '../../utils/testScopeAnalysis'
import { TestScopeEvidence } from './TestScopeEvidence'
import {
  CATEGORY_DOT_TONE,
  CATEGORY_PILL,
  CATEGORY_PILL_TONE,
  DETAIL_FOOT,
  DETAIL_TITLE,
  ID_CHIP,
  ICON_BUTTON,
  JUDGEMENT,
  JUDGEMENT_LABEL,
  JUDGEMENT_TEXT,
  META_ROW,
  QUESTION_NOTE,
  RELATIONS,
  RELATION_CHIPS,
  RELATION_GRID,
  RELATION_LABEL,
  REL_CHIP,
  REL_CHIP_ARROW,
  REL_CHIP_CODE,
  REL_CHIP_TITLE,
  STAT_CELL,
  STAT_LABEL,
  STAT_STRIP,
  STAT_VALUE,
  STATUS_DOT,
  STATUS_DOT_TONE,
  STATUS_PILL,
  STATUS_PILL_TONE,
  TYPE_CHIP,
} from './testScopeClasses'

const JUDGEMENT_LABEL_BY_CATEGORY: Record<ScopeCategoryKey, string> = {
  testObjects: '范围判断',
  impactAreas: '影响判断',
  risks: '风险说明',
  openQuestions: '问题背景',
}

function StatStrip({ entry, category }: { entry: ScopeEntryView; category: ScopeCategoryKey }) {
  const count = (key: ScopeCategoryKey) => entry.relationIds[key]?.length ?? 0
  const items = category === 'testObjects'
    ? [
      { label: '材料依据', value: entry.sourceBlockIds.length },
      { label: '关联影响', value: count('impactAreas') },
      { label: '关联风险', value: count('risks') },
      { label: '关联待确认', value: count('openQuestions') },
    ]
    : category === 'impactAreas'
      ? [
        { label: '关联对象', value: count('testObjects') },
        { label: '关联风险', value: count('risks') },
        { label: '关联待确认', value: count('openQuestions') },
        { label: '材料依据', value: entry.sourceBlockIds.length },
      ]
      : category === 'risks'
        ? [
          { label: '关联对象', value: count('testObjects') },
          { label: '关联影响', value: count('impactAreas') },
          { label: '关联待确认', value: count('openQuestions') },
          { label: '材料依据', value: entry.sourceBlockIds.length },
        ]
        : [
          { label: '关联对象', value: count('testObjects') },
          { label: '关联影响', value: count('impactAreas') },
          { label: '关联风险', value: count('risks') },
          { label: '材料依据', value: entry.sourceBlockIds.length },
        ]
  return <div className={STAT_STRIP} aria-label="条目摘要">
    {items.map((item) => <div className={STAT_CELL} key={item.label}>
      <span className={STAT_LABEL}>{item.label}</span>
      <span className={STAT_VALUE}>{item.value}</span>
    </div>)}
  </div>
}

function RelationChips({ entry, category, view, onJump }: {
  entry: ScopeEntryView
  category: ScopeCategoryKey
  view: TestScopeView
  onJump: (category: ScopeCategoryKey, id: string) => void
}) {
  const rows = relationRows(entry, category, view)
  const sourceQuestions = entry.sourceQuestionIds
  if (!rows.length && !sourceQuestions.length) return null
  return <div className={RELATIONS}>
    {rows.map((row) => {
      const targetCategory = view.categories[row.category]
      return <div className={RELATION_GRID} key={row.category}>
        <span className={RELATION_LABEL}>{row.label}</span>
        <div className={RELATION_CHIPS}>
          {row.items.map((item) => <button
            key={item.id}
            type="button"
            className={cx(REL_CHIP, 'max-w-[360px] max-narrow-sm:max-w-full')}
            aria-label={`查看${targetCategory.label} ${item.id}：${item.title}`}
            title={item.title}
            onClick={() => onJump(row.category, item.id)}
          >
            <span className={cx('size-[5px] shrink-0 rounded-full', CATEGORY_DOT_TONE[targetCategory.tone])} aria-hidden="true" />
            <code className={REL_CHIP_CODE}>{item.id}</code>
            <span className={REL_CHIP_TITLE}>{item.title}</span>
            <ArrowRightOutlined className={REL_CHIP_ARROW} aria-hidden="true" />
          </button>)}
        </div>
      </div>
    })}
    {sourceQuestions.length ? <div className={RELATION_GRID}>
      <span className={RELATION_LABEL}>来源问题</span>
      <div className={RELATION_CHIPS}>
        {sourceQuestions.map((id) => <span key={id} className="inline-flex max-w-full items-center rounded-[6px] border border-app-surface-border bg-app-surface px-2 py-1 text-[11px] leading-[1.4] text-app-surface-text-muted">
          <span className="min-w-0 truncate">{view.sourceQuestionById.get(id) || id}</span>
        </span>)}
      </div>
    </div> : null}
  </div>
}

export function TestScopeDetail({ category, entry, view, onJump, onCopy }: {
  category: ScopeCategoryView
  entry?: ScopeEntryView
  view: TestScopeView
  onJump: (category: ScopeCategoryKey, id: string) => void
  onCopy: (id: string) => void
}) {
  if (!entry) {
    return <section aria-label={`${category.label}详情`} className="flex min-h-[420px] flex-col items-center justify-center gap-3 px-4 py-10">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={<span className="text-[12px] text-app-surface-text-muted">暂无{category.label}</span>}
      />
    </section>
  }

  const meta = SCOPE_STATUS[entry.status]
  const statusMarkup = category.key === 'openQuestions'
    ? null
    : <span className={cx(STATUS_PILL, STATUS_PILL_TONE[meta.tone])}><span className={cx(STATUS_DOT, STATUS_DOT_TONE[meta.tone])} aria-hidden="true" />{meta.label}</span>

  return <section aria-label={`${category.label}详情`} className="min-w-0">
    <h2 className={DETAIL_TITLE}>{entry.title}</h2>
    <div className={META_ROW}>
      <span className={cx(CATEGORY_PILL, CATEGORY_PILL_TONE[category.tone])}>{category.label}</span>
      <code className={ID_CHIP}>{entry.id}</code>
      {statusMarkup}
      {entry.type ? <span className={TYPE_CHIP}>{entry.type}</span> : null}
      <button type="button" className={ICON_BUTTON} aria-label={`复制 ID ${entry.id}`} title="复制 ID" onClick={() => onCopy(entry.id)}>
        <CopyOutlined aria-hidden="true" />
      </button>
    </div>

    {category.key === 'openQuestions' ? <div className={QUESTION_NOTE}>
      <WarningOutlined className="mt-0.5 shrink-0 text-app-status-warning-text" aria-hidden="true" />
      <span><strong className="font-semibold text-app-status-warning-text">材料未明确</strong>，建议在生成用例前补充确认，不把推测写成事实。</span>
    </div> : null}

    <div className={JUDGEMENT}>
      <span className={JUDGEMENT_LABEL}>{JUDGEMENT_LABEL_BY_CATEGORY[category.key]}</span>
      <p className={JUDGEMENT_TEXT}>{entry.narrative}</p>
    </div>

    <StatStrip entry={entry} category={category.key} />
    <RelationChips entry={entry} category={category.key} view={view} onJump={onJump} />
    <TestScopeEvidence entry={entry} blockById={view.blockById} />

    <div className={DETAIL_FOOT}><LockOutlined aria-hidden="true" />分析结果只读，生成用例时按此范围执行。</div>
  </section>
}
