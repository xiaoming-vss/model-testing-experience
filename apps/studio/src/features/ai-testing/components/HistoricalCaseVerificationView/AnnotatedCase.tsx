import { InfoCircleOutlined } from '@ant-design/icons'
import { Fragment } from 'react'
import { cx } from '@/shared/utils/cx'
import { SECTION, SECTION_COUNT, SECTION_HEAD, SECTION_NOTE, SECTION_TITLE } from '../TestScopeAnalysisView/testScopeClasses'
import { HistoricalTag } from '../HistoricalRelationView/HistoricalTag'
import {
  ANNOTATION, ANNOTATION_HEAD, ANNOTATION_NOTE, ANNOTATION_TEXT, DOC_CELL, DOC_EMPTY_CELL, DOC_HEAD, DOC_HEAD_NOTE,
  DOC_HEAD_TITLE, DOC_EMPTY, DOC_ITEM, DOC_LIST, DOC_NO, DOC_NO_CELL, DOC_NOTE_CELL, DOC_NOTES, DOC_TABLE, DOC_TABLE_HEAD, DOC_TEXT,
  EDGE, FLAG_BAR, FLAG_BG, HINT, HINT_LABEL, NOTE_INFO, OTHER_RULE, OTHER_RULES, PILL_INFO,
} from './historicalCaseVerificationClasses'
import { batchTitle, decisionRank, type CaseFindingView, type CaseSnapshotView, type DecisionTone } from '../../utils/historicalCaseVerificationView'

const NO_SNAPSHOT = '前置条件和步骤原文来自冻结的核验输入，当前接口未返回。'
const evidenceKey = (item: { kind: string; position: number }) => `${item.kind}:${item.position}`
const evidenceLabel = (item: { kind: string; position: number }) => `${item.kind === 'precondition' ? '前置条件' : '步骤'} ${item.position}`

/** 证据位置 → 落在该位置上的结论。 */
function groupByPosition(findings: CaseFindingView[]) {
  const grouped = new Map<string, CaseFindingView[]>()
  findings.forEach((finding) => {
    finding.evidence.forEach((item) => {
      const key = evidenceKey(item)
      grouped.set(key, [...(grouped.get(key) ?? []), finding])
    })
  })
  return grouped
}

/** 同一位置有多条结论时，按最需要处理的那条着色。 */
const strongestTone = (findings: CaseFindingView[]): DecisionTone => findings.reduce((best, finding) =>
  decisionRank(finding.decision.key) < decisionRank(best.decision.key) ? finding : best).decision.tone

/** 结论是否来自补读全文之后。 */
export function Provenance({ finding }: { finding: CaseFindingView }) {
  return finding.fullCase ? <span className={PILL_INFO}>补读全文后</span> : null
}

/**
 * 一条结论在某个位置上的批注。同一条结论引用多个位置时只在首个位置给出理由和建议，
 * 其余位置留简短标记；current 标出是从哪条结论打开的。
 */
function Annotation({ finding, current, compact }: { finding: CaseFindingView; current?: CaseFindingView; compact: boolean }) {
  const note = compact
    ? <span className={ANNOTATION_NOTE}>同一条结论，理由与建议见{evidenceLabel(finding.evidence[0])}</span>
    : finding === current
      ? <span className={PILL_INFO}>当前规则</span>
      : <span className={ANNOTATION_NOTE}>关联规则：{batchTitle(finding.batch)}</span>
  return <div className={cx(ANNOTATION, EDGE[finding.decision.tone])}>
    <div className={ANNOTATION_HEAD}>
      <HistoricalTag value={finding.decision} />
      <Provenance finding={finding} />
      {note}
    </div>
    {compact ? null : <p className={ANNOTATION_TEXT}>{finding.reason}</p>}
    {compact || !finding.modificationHint ? null : <div className={HINT}><span className={HINT_LABEL}>建议改为</span><span>{finding.modificationHint}</span></div>}
  </div>
}

/** 冻结输入不可用时，说明原文为什么显示不出来。 */
export function NoSnapshotNote() {
  return <div className={cx('mt-4', NOTE_INFO)} role="note"><InfoCircleOutlined className="mt-0.5 shrink-0 text-app-accent" aria-hidden="true" /><span>{NO_SNAPSHOT}</span></div>
}

/**
 * 用例全文（核验时的冻结快照）加上各条结论的行内批注。
 * current：从规则档案的某条结论打开时传入，用来标出当前规则并列出该用例在其他规则下的结论。
 * standalone：作为用例档案正文时使用档案级标题。
 */
export function AnnotatedCase({ snapshot, findings, current, standalone = false }: {
  snapshot: CaseSnapshotView
  findings: CaseFindingView[]
  current?: CaseFindingView
  standalone?: boolean
}) {
  const grouped = groupByPosition(findings)
  const others = current ? findings.filter(finding => finding !== current) : []
  const notes = (key: string) => grouped.get(key) ?? []
  const flagged = (key: string) => notes(key).length > 0
  const background = (key: string) => (flagged(key) ? FLAG_BG[strongestTone(notes(key))] : undefined)
  const bar = (key: string) => (flagged(key) ? FLAG_BAR[strongestTone(notes(key))] : undefined)
  const annotations = (key: string) => notes(key).map(finding => (
    <Annotation key={finding.id} finding={finding} current={current} compact={key !== evidenceKey(finding.evidence[0])} />
  ))
  const head = (title: string, count: number, note?: string) => (standalone
    ? <header className={SECTION_HEAD}><h2 className={SECTION_TITLE}>{title}</h2><span className={SECTION_COUNT}>{count}</span>{note ? <span className={SECTION_NOTE}>{note}</span> : null}</header>
    : <header className={DOC_HEAD}><h4 className={DOC_HEAD_TITLE}>{title}</h4><span className={SECTION_COUNT}>{count}</span>{note ? <span className={DOC_HEAD_NOTE}>{note}</span> : null}</header>)
  return <>
    {others.length ? <div className={OTHER_RULES} role="note" aria-label="其他规则下的结论">
      <span>该用例在其他规则下的结论</span>
      {others.map(finding => (
        <span key={finding.id} className={OTHER_RULE}>
          <HistoricalTag value={finding.decision} />
          {batchTitle(finding.batch)}
        </span>
      ))}
    </div> : null}
    <section className={standalone ? SECTION : undefined} aria-label="前置条件">
      {head('前置条件', snapshot.preconditions.length)}
      <ol className={DOC_LIST}>
        {snapshot.preconditions.length ? snapshot.preconditions.map((line) => {
          const key = `precondition:${line.position}`
          return <li key={line.position} className={cx(DOC_ITEM, background(key), bar(key))}>
            <span className={DOC_NO}>{line.position}</span>
            <span className={DOC_TEXT}>{line.text}</span>
            {flagged(key) ? <div className={DOC_NOTES}>{annotations(key)}</div> : null}
          </li>
        }) : <li className={DOC_EMPTY}>没有前置条件</li>}
      </ol>
    </section>
    <section className={standalone ? SECTION : undefined} aria-label="操作步骤">
      {head('操作步骤', snapshot.steps.length, '标出的位置即结论引用的证据')}
      <table className={DOC_TABLE}>
        <colgroup><col style={{ width: 44 }} /><col style={{ width: '50%' }} /><col /></colgroup>
        <thead><tr><th className={DOC_TABLE_HEAD}>#</th><th className={DOC_TABLE_HEAD}>操作</th><th className={DOC_TABLE_HEAD}>预期</th></tr></thead>
        <tbody>{snapshot.steps.map((step) => {
          const key = `step:${step.position}`
          return <Fragment key={step.position}>
            <tr className={background(key)}>
              <td className={cx(DOC_NO_CELL, bar(key))}>{step.position}</td>
              <td className={DOC_CELL}>{step.action}</td>
              <td className={DOC_CELL}>{step.expected}</td>
            </tr>
            {flagged(key) ? <tr className={background(key)}>
              <td className={DOC_EMPTY_CELL} aria-hidden="true" />
              <td colSpan={2} className={DOC_NOTE_CELL}>{annotations(key)}</td>
            </tr> : null}
          </Fragment>
        })}</tbody>
      </table>
    </section>
  </>
}
