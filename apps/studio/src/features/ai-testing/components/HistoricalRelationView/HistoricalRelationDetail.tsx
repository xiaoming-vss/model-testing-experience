import { ArrowRightOutlined, LockOutlined, RightOutlined, WarningOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import {
  REVIEW_STATUS,
  type HistoricalImpactView,
  type HistoricalItemView,
  type HistoricalQuestionView,
  type HistoricalRelationData,
  type HistoricalRelationView,
} from '../../utils/historicalRelationView'
import {
  DETAIL_FOOT,
  DETAIL_TITLE,
  EVIDENCE_CARD,
  EVIDENCE_EMPTY,
  ID_CHIP,
  JUDGEMENT,
  JUDGEMENT_LABEL,
  JUDGEMENT_TEXT,
  META_ROW,
  QUESTION_NOTE,
  REL_CHIP,
  REL_CHIP_ARROW,
  REL_CHIP_TITLE,
  SECTION,
  SECTION_COUNT,
  SECTION_HEAD,
  SECTION_NOTE,
  SECTION_TITLE,
  STAT_CELL,
  STAT_LABEL,
  STAT_STRIP,
  STAT_VALUE,
  STATUS_DOT,
  STATUS_PILL,
  TYPE_CHIP,
} from '../TestScopeAnalysisView/testScopeClasses'
import type { HistoricalRelationCategory } from './HistoricalRelationRail'
import { HistoricalTag as Tag } from './HistoricalTag'
import { RuleCompare } from './RuleCompare'
import {
  EVIDENCE_CHEVRON,
  EVIDENCE_LOC,
  EVIDENCE_ROW,
  EVIDENCE_ROWS,
  EVIDENCE_SIDE,
  EVIDENCE_TEXT,
  EVIDENCE_TOGGLE,
  ID_CHIP_CLIP,
  IMPACT,
  IMPACT_SUMMARY,
  IMPACT_TAGS,
  JUMP_LINK,
  KNOWN_ITEM,
  KNOWN_LIST,
  NOTE_ICON,
  TONE_COLOR,
  TONE_PILL,
} from './historicalRelationClasses'

function evidenceRows(impact: HistoricalImpactView): Array<{ side: string; item: HistoricalItemView }> {
  return [
    ...impact.historical.map((item) => ({ side: '历史材料', item })),
    ...impact.current.map((item) => ({ side: '本次材料', item })),
  ]
}

function EvidenceRows({ impact }: { impact: HistoricalImpactView }) {
  return <div className={EVIDENCE_ROWS}>
    {evidenceRows(impact).map(({ side, item }) => <div className={EVIDENCE_ROW} key={`${side}:${item.id}`}>
      <span className={EVIDENCE_SIDE}>{side}</span>
      <div className="min-w-0">
        <div className={EVIDENCE_LOC}>
          {item.status ? <Tag value={item.status} /> : null}
          {item.functionName ? <span>{item.functionName} · {item.sectionTitle}</span> : null}
          <code className={ID_CHIP}>{item.id}</code>
        </div>
        <p className={cx(EVIDENCE_TEXT, !item.text && 'text-app-surface-text-muted')}>
          {item.text || '条目原文不可用，仅显示条目引用。'}
        </p>
      </div>
    </div>)}
  </div>
}

/** 一条规则影响：历史规则与本次规则并排对照，后接适用范围和两侧冻结条目。 */
function ImpactBlock({ impact, onJumpQuestion }: {
  impact: HistoricalImpactView
  onJumpQuestion: (question: HistoricalQuestionView) => void
}) {
  return <section className={IMPACT} data-impact-id={impact.id} aria-label={`规则影响 ${impact.id}`}>
    <div className={IMPACT_TAGS}>
      <Tag value={impact.effect} />
      <Tag value={impact.status} />
      <code className={ID_CHIP}>{impact.id}</code>
    </div>
    <p className={IMPACT_SUMMARY}>{impact.summary}</p>
    <RuleCompare rule={impact} />
    <details className={cx(EVIDENCE_CARD, 'group')}>
      <summary className={EVIDENCE_TOGGLE}>
        <span>材料依据</span>
        <span className={SECTION_COUNT}>{impact.historical.length + impact.current.length}</span>
        <span className="text-app-surface-text-muted">条冻结条目</span>
        <RightOutlined className={EVIDENCE_CHEVRON} aria-hidden="true" />
      </summary>
      <EvidenceRows impact={impact} />
    </details>
    {impact.questions.map((question) => <div className={QUESTION_NOTE} key={question.id}>
      <WarningOutlined className={NOTE_ICON} aria-hidden="true" />
      <span>{question.question}</span>
      <button type="button" className={JUMP_LINK} onClick={() => onJumpQuestion(question)}>查看问题</button>
    </div>)}
  </section>
}

function RelationArchive({ relation, data, requirementName, onJumpQuestion }: {
  relation: HistoricalRelationView
  data: HistoricalRelationData
  requirementName: (id: string) => string
  onJumpQuestion: (question: HistoricalQuestionView) => void
}) {
  const needs = relation.impacts.filter((impact) => impact.status.key === 'needs_confirmation').length
  const proposed = REVIEW_STATUS.proposed.label
  const pending = REVIEW_STATUS.needs_confirmation.label
  const known = data.knownRelations.filter((edge) => edge.from === relation.requirementId || edge.to === relation.requirementId)
  const stats: Array<[string, number]> = [
    ['规则影响', relation.impacts.length],
    [proposed, relation.impacts.length - needs],
    [pending, needs],
    ['引用本次条目', new Set(relation.impacts.flatMap((impact) => impact.current.map((item) => item.id))).size],
  ]
  return <section aria-label="关联需求详情" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{relation.name}</h2>
    <div className={META_ROW}>
      <Tag value={relation.type} />
      <code className={cx(ID_CHIP, ID_CHIP_CLIP)} title={relation.requirementId}>{relation.requirementId}</code>
      {relation.sprintName ? <span className={TYPE_CHIP}>{relation.sprintName}</span> : null}
    </div>

    <div className={JUDGEMENT}>
      <span className={JUDGEMENT_LABEL}>关联说明</span>
      <p className={JUDGEMENT_TEXT}>
        本次需求对该历史需求的主要动作是「{relation.type.label}」：共 {relation.impacts.length} 项规则影响，其中 {relation.impacts.length - needs} 项{proposed}、{needs} 项{pending}。
      </p>
    </div>

    <div className={STAT_STRIP} role="group" aria-label="关联摘要">
      {stats.map(([label, value]) => <div className={STAT_CELL} key={label}>
        <span className={STAT_LABEL}>{label}</span>
        <span className={STAT_VALUE}>{value}</span>
      </div>)}
    </div>

    <section className={SECTION} aria-label="规则影响">
      <div className={SECTION_HEAD}>
        <h2 className={SECTION_TITLE}>规则影响</h2>
        <span className={SECTION_COUNT}>{relation.impacts.length}</span>
      </div>
      {relation.impacts.length
        ? relation.impacts.map((impact) => <ImpactBlock key={impact.id} impact={impact} onJumpQuestion={onJumpQuestion} />)
        : <p className={EVIDENCE_EMPTY}>该关联下没有可展示的规则影响。</p>}
    </section>

    {known.length ? <section className={SECTION} aria-label="已确认历史关系">
      <div className={SECTION_HEAD}>
        <h2 className={SECTION_TITLE}>已确认历史关系</h2>
        <span className={SECTION_NOTE}><LockOutlined aria-hidden="true" />冻结输入中由历史快照支持</span>
      </div>
      <div className={KNOWN_LIST}>
        {known.map((edge) => <span className={KNOWN_ITEM} key={`${edge.from}:${edge.type.key}:${edge.to}`}>
          <span className={TYPE_CHIP}>{requirementName(edge.from)}</span>
          <ArrowRightOutlined className={REL_CHIP_ARROW} aria-hidden="true" />
          <Tag value={edge.type} />
          <span className={TYPE_CHIP}>{requirementName(edge.to)}</span>
        </span>)}
      </div>
    </section> : null}

    <div className={DETAIL_FOOT}>
      <LockOutlined aria-hidden="true" />
      {relation.snapshotId ? `只读，基于历史材料快照 ${relation.snapshotId}。` : '只读。'}
    </div>
  </section>
}

function QuestionArchive({ question, onJumpImpact }: {
  question: HistoricalQuestionView
  onJumpImpact: (impact: HistoricalImpactView) => void
}) {
  const impact = question.impact
  return <section aria-label="待确认问题详情" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{question.question}</h2>
    <div className={META_ROW}>
      <span className={cx(STATUS_PILL, TONE_PILL.warn)}>
        <span className={cx(STATUS_DOT, TONE_COLOR.warn)} aria-hidden="true" />
        {REVIEW_STATUS.needs_confirmation.label}
      </span>
      <code className={ID_CHIP}>{question.id}</code>
    </div>

    <div className={QUESTION_NOTE}>
      <WarningOutlined className={NOTE_ICON} aria-hidden="true" />
      <span>需要向业务方确认的问题；确认前请人工判断是否采用关联规则。</span>
    </div>

    <section className={SECTION} aria-label="关联规则">
      <div className={SECTION_HEAD}><h2 className={SECTION_TITLE}>关联规则</h2></div>
      {impact
        ? <button type="button" className={cx(REL_CHIP, 'max-w-full')} onClick={() => onJumpImpact(impact)}>
            <span className={cx(STATUS_DOT, TONE_COLOR[impact.effect.tone])} aria-hidden="true" />
            <span className={REL_CHIP_TITLE}>{impact.relation.name}</span>
            <Tag value={impact.effect} />
            <ArrowRightOutlined className={REL_CHIP_ARROW} aria-hidden="true" />
          </button>
        : <p className={EVIDENCE_EMPTY}>尚未定位到一条具体规则。</p>}
    </section>

    <section className={SECTION} aria-label="材料依据">
      <div className={SECTION_HEAD}>
        <h2 className={SECTION_TITLE}>材料依据</h2>
        {impact ? <span className={SECTION_COUNT}>{evidenceRows(impact).length}</span> : null}
      </div>
      {impact ? <EvidenceRows impact={impact} /> : <p className={EVIDENCE_EMPTY}>暂无材料依据。</p>}
    </section>
  </section>
}

/** 关联需求档案或待确认问题档案；调用方保证当前分类下有选中项。 */
export function HistoricalRelationDetail({ category, relation, question, data, requirementName, onJumpQuestion, onJumpImpact }: {
  category: HistoricalRelationCategory
  relation?: HistoricalRelationView
  question?: HistoricalQuestionView
  data: HistoricalRelationData
  requirementName: (id: string) => string
  onJumpQuestion: (question: HistoricalQuestionView) => void
  onJumpImpact: (impact: HistoricalImpactView) => void
}) {
  if (category === 'questions') {
    return question ? <QuestionArchive question={question} onJumpImpact={onJumpImpact} /> : null
  }
  return relation
    ? <RelationArchive relation={relation} data={data} requirementName={requirementName} onJumpQuestion={onJumpQuestion} />
    : null
}
