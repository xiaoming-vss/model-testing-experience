import { RightOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import {
  DETAIL_TITLE, ID_CHIP, META_ROW, SECTION, SECTION_COUNT, SECTION_HEAD, SECTION_NOTE, SECTION_TITLE,
  STAT_CELL, STAT_LABEL, STAT_STRIP, STAT_VALUE, TYPE_CHIP,
} from '../TestScopeAnalysisView/testScopeClasses'
import { ID_CHIP_CLIP } from '../HistoricalRelationView/historicalRelationClasses'
import { HistoricalTag } from '../HistoricalRelationView/HistoricalTag'
import { RuleCompare } from '../HistoricalRelationView/RuleCompare'
import { AnnotatedCase, NoSnapshotNote, Provenance } from './AnnotatedCase'
import {
  CASE_ID, EVIDENCE_ARROW, EVIDENCE_KIND, EVIDENCE_LINE, EVIDENCE_LINES, EVIDENCE_TEXT, FINDING, FINDING_HEAD, FINDING_META,
  FINDING_OPEN, FINDING_TITLE, FINDING_TOGGLE, HINT, HINT_LABEL, KV, KV_VALUE, KV_LABEL, SUPPLEMENTAL_POINT,
} from './historicalCaseVerificationClasses'
import { batchTitle, CASE_DECISION, findingTitle, REVIEW_DECISIONS, type CaseFindingView, type VerificationBatchView } from '../../utils/historicalCaseVerificationView'

/** 规则档案、用例档案和导航之间共用的查找与操作。 */
export type VerificationLookup = {
  requirementName: (requirementId: string) => string
  suiteName: (suiteId: string) => string
  /** 同一条用例在所有规则下的结论。 */
  caseFindings: (caseId: string) => CaseFindingView[]
  isExpanded: (findingId: string) => boolean
  toggle: (findingId: string) => void
  /** 回到规则档案；带结论时直接展开那一条。 */
  openRule: (batchId: string, findingId?: string) => void
}

/** 结论引用的证据位置；冻结输入不可用时只显示位置编号。 */
export function EvidenceLines({ finding }: { finding: CaseFindingView }) {
  if (!finding.evidence.length) return <span className="text-app-surface-text-muted">未引用具体位置</span>
  return <div className={EVIDENCE_LINES}>
    {finding.evidence.map((item) => (
      <div key={`${item.kind}:${item.position}`} className={EVIDENCE_LINE}>
        <span className={EVIDENCE_KIND}>{item.kind === 'precondition' ? '前置条件' : '步骤'} {item.position}</span>
        {item.text === null
          ? <span className={cx(EVIDENCE_TEXT, 'text-app-surface-text-muted')}>位置原文不可用，仅显示位置</span>
          : <span className={EVIDENCE_TEXT}>
              {item.text}
              {item.expected === null ? null : <><i className={EVIDENCE_ARROW}>→</i>{item.expected}</>}
            </span>}
      </div>
    ))}
  </div>
}

function FindingSummary({ finding }: { finding: CaseFindingView }) {
  return <dl className={KV}>
    <dt className={KV_LABEL}>证据</dt>
    <dd className={KV_VALUE}><EvidenceLines finding={finding} /></dd>
    <dt className={KV_LABEL}>理由</dt>
    <dd className={KV_VALUE}>{finding.reason}</dd>
    {finding.modificationHint ? <>
      <dt className={KV_LABEL}>建议</dt>
      <dd className={KV_VALUE}><div className={HINT}><span className={HINT_LABEL}>建议改为</span><span>{finding.modificationHint}</span></div></dd>
    </> : null}
  </dl>
}

/** 一条用例结论：收起时是摘要，展开后原地换成带行内批注的完整用例。 */
function FindingCard({ finding, caseFindings, open, suiteName, onToggle }: {
  finding: CaseFindingView
  caseFindings: CaseFindingView[]
  open: boolean
  suiteName: (suiteId: string) => string
  onToggle: () => void
}) {
  const snapshot = finding.snapshot
  const suite = snapshot ? suiteName(snapshot.suiteId) : ''
  const context = [snapshot?.module, suite].filter(Boolean).join(' · ')
  return <section className={open ? FINDING_OPEN : FINDING} data-finding-id={finding.id} aria-label={`用例结论 ${finding.decision.label}`}>
    <div className={FINDING_HEAD}>
      <HistoricalTag value={finding.decision} />
      <Provenance finding={finding} />
      <code className={CASE_ID} title={finding.caseId}>{finding.caseId.slice(0, 8)}</code>
      {context ? <span className={FINDING_META}>{context}</span> : null}
      <button
        type="button"
        className={FINDING_TOGGLE}
        aria-expanded={open}
        disabled={!snapshot}
        title={snapshot ? undefined : '前置条件和步骤原文来自冻结的核验输入，当前接口未返回'}
        onClick={onToggle}
      >
        {open ? '收起完整用例' : '在完整用例中查看'}
        <RightOutlined className={cx('text-[10px] transition-transform', open && 'rotate-90')} aria-hidden="true" />
      </button>
    </div>
    <h3 className={FINDING_TITLE}>{findingTitle(finding)}</h3>
    {open && snapshot
      ? <AnnotatedCase snapshot={snapshot} findings={caseFindings} current={finding} />
      : <FindingSummary finding={finding} />}
  </section>
}

/** 一条规则的核验档案：规则对照、需处理的用例结论和补测测试点。 */
export function RuleVerificationArchive({ batch, lookup }: { batch: VerificationBatchView; lookup: VerificationLookup }) {
  const stats: Array<[string, number]> = [
    ...REVIEW_DECISIONS.map((key): [string, number] => [
      CASE_DECISION[key].label, batch.findings.filter(finding => finding.decision.key === key).length,
    ]),
    ['补测测试点', batch.points.length],
  ]
  const historyName = batch.historyRequirementId ? lookup.requirementName(batch.historyRequirementId) : ''
  return <section aria-label="规则核验档案" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{batchTitle(batch)}</h2>
    <div className={META_ROW}>
      {batch.effect ? <HistoricalTag value={batch.effect} /> : null}
      <code className={cx(ID_CHIP, ID_CHIP_CLIP)} title={batch.impactId}>{batch.impactId}</code>
      {historyName ? <span className={TYPE_CHIP}>历史需求 · {historyName}</span> : null}
      <code className={cx(ID_CHIP, ID_CHIP_CLIP)} title={batch.id}>{batch.id}</code>
    </div>
    <div className="mt-4">{batch.rule ? <RuleCompare rule={batch.rule} /> : <NoSnapshotNote />}</div>
    <div className={STAT_STRIP} role="group" aria-label="规则摘要">
      {stats.map(([label, value]) => <div className={STAT_CELL} key={label}>
        <span className={STAT_LABEL}>{label}</span>
        <span className={STAT_VALUE}>{value}</span>
      </div>)}
    </div>
    <section className={SECTION} aria-label="用例结论">
      <div className={SECTION_HEAD}>
        <h2 className={SECTION_TITLE}>用例结论</h2>
        <span className={SECTION_COUNT}>{batch.findings.length}</span>
        {batch.findings.length ? null : <span className={SECTION_NOTE}>没有需要处理的历史用例</span>}
      </div>
      {batch.findings.map(finding => (
        <FindingCard
          key={finding.id}
          finding={finding}
          caseFindings={lookup.caseFindings(finding.caseId)}
          open={lookup.isExpanded(finding.id)}
          suiteName={lookup.suiteName}
          onToggle={() => lookup.toggle(finding.id)}
        />
      ))}
    </section>
    <section className={SECTION} aria-label="补测测试点">
      <div className={SECTION_HEAD}>
        <h2 className={SECTION_TITLE}>补测测试点</h2>
        <span className={SECTION_COUNT}>{batch.points.length}</span>
      </div>
      {batch.points.map(point => <p className={SUPPLEMENTAL_POINT} key={point.id}>{point.title}</p>)}
    </section>
  </section>
}
