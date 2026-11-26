import { LockOutlined, WarningOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import { DETAIL_FOOT, DETAIL_TITLE, ID_CHIP, META_ROW, SECTION, SECTION_HEAD, SECTION_TITLE, TYPE_CHIP } from '../TestScopeAnalysisView/testScopeClasses'
import { HistoricalTag } from '../HistoricalRelationView/HistoricalTag'
import { RuleCompare } from '../HistoricalRelationView/RuleCompare'
import { AnnotatedCase, NoSnapshotNote, Provenance } from './AnnotatedCase'
import { EvidenceLines, RuleVerificationArchive, type VerificationLookup } from './RuleVerificationDetail'
import type { VerificationCategory } from './verificationListing'
import {
  ANNOTATION_TEXT, CASE_ID, EDGE, FINDING_META, HINT, HINT_LABEL, JUMP_LINK, NOTE_REVIEW,
  VERDICT, VERDICT_RULE, VERDICT_TAGS, VERDICTS,
} from './historicalCaseVerificationClasses'
import { batchTitle, decisionTags, findingTitle, type CaseFindingView, type SupplementalPointView, type VerificationBatchView, type VerificationCaseView } from '../../utils/historicalCaseVerificationView'

const contextOf = (finding: CaseFindingView, lookup: VerificationLookup) => (
  [finding.snapshot?.module, finding.snapshot ? lookup.suiteName(finding.snapshot.suiteId) : ''].filter(Boolean).join(' · ')
)

/** 一条历史用例的档案：先列它在每条规则下的结论，再给带行内批注的完整用例。 */
function CaseArchive({ item, lookup }: { item: VerificationCaseView; lookup: VerificationLookup }) {
  const [first] = item.findings
  const snapshot = first.snapshot
  const decisions = decisionTags(item.findings)
  const context = contextOf(first, lookup)
  return <section aria-label="历史用例档案" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{findingTitle(first)}</h2>
    <div className={META_ROW}>
      {decisions.map(decision => <HistoricalTag key={decision.key} value={decision} />)}
      <code className={CASE_ID} title={first.caseId}>{first.caseId.slice(0, 8)}</code>
      {context ? <span className={TYPE_CHIP}>{context}</span> : null}
    </div>
    <div className={VERDICTS}>
      {item.findings.map(finding => <div key={finding.id} className={cx(VERDICT, EDGE[finding.decision.tone])}>
        <div className={VERDICT_TAGS}>
          <HistoricalTag value={finding.decision} />
          <Provenance finding={finding} />
          <span className={VERDICT_RULE}>关联规则：{batchTitle(finding.batch)}</span>
          <button type="button" className={JUMP_LINK} onClick={() => lookup.openRule(finding.batch.id, finding.id)}>在规则档案中查看</button>
        </div>
        <p className={ANNOTATION_TEXT}>{finding.reason}</p>
        {finding.modificationHint || !snapshot ? <div className="mt-2 flex flex-col gap-2">
          {finding.modificationHint ? <div className={HINT}><span className={HINT_LABEL}>建议改为</span><span>{finding.modificationHint}</span></div> : null}
          {snapshot ? null : <EvidenceLines finding={finding} />}
        </div> : null}
      </div>)}
    </div>
    {snapshot ? <AnnotatedCase snapshot={snapshot} findings={item.findings} standalone /> : <NoSnapshotNote />}
    <div className={DETAIL_FOOT}>
      <LockOutlined aria-hidden="true" />
      只读 · 核验基于用例快照 <code className={ID_CHIP}>{first.caseSnapshotId}</code>；采用只保存分析结果，用例的修改与失效在用例库处理。
    </div>
  </section>
}

function SupplementalPointArchive({ point, lookup }: { point: SupplementalPointView; lookup: VerificationLookup }) {
  return <section aria-label="补测测试点档案" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{point.title}</h2>
    <RelatedRule batch={point.batch} lookup={lookup} />
  </section>
}

/** 待确认的用例：规则适用或用例内容不足以支持结论，指明缺少的事实。 */
function PendingArchive({ finding, lookup }: { finding: CaseFindingView; lookup: VerificationLookup }) {
  const context = contextOf(finding, lookup)
  return <section aria-label="待确认用例档案" className="min-w-0">
    <h2 className={DETAIL_TITLE}>{findingTitle(finding)}</h2>
    <div className={META_ROW}>
      <HistoricalTag value={finding.decision} />
      <Provenance finding={finding} />
      <code className={CASE_ID} title={finding.caseId}>{finding.caseId.slice(0, 8)}</code>
      {context ? <span className={TYPE_CHIP}>{context}</span> : null}
      <span className={FINDING_META}>来自规则</span>
      {finding.batch.effect ? <HistoricalTag value={finding.batch.effect} /> : null}
      <span className={TYPE_CHIP}>{batchTitle(finding.batch)}</span>
    </div>
    <div className={cx('mt-4', NOTE_REVIEW)} role="note">
      <WarningOutlined className="mt-0.5 shrink-0 text-[var(--app-status-review-text)]" aria-hidden="true" />
      <span><strong className="font-semibold">规则适用或用例内容不足以支持结论。</strong>{finding.reason}</span>
    </div>
    <section className={SECTION} aria-label="证据位置">
      <div className={SECTION_HEAD}><h2 className={SECTION_TITLE}>证据位置</h2></div>
      <EvidenceLines finding={finding} />
    </section>
    <RelatedRule batch={finding.batch} lookup={lookup} findingId={finding.id} />
  </section>
}

function RelatedRule({ batch, lookup, findingId }: { batch: VerificationBatchView; lookup: VerificationLookup; findingId?: string }) {
  return <section className={SECTION} aria-label="所属规则">
    <div className={SECTION_HEAD}>
      <h2 className={SECTION_TITLE}>所属规则</h2>
      <button type="button" className={JUMP_LINK} onClick={() => lookup.openRule(batch.id, findingId)}>在规则档案中查看</button>
    </div>
    {batch.rule ? <RuleCompare rule={batch.rule} /> : <NoSnapshotNote />}
  </section>
}

/** 按当前分类给出用例档案、补测测试点档案、待确认档案或规则核验档案；没有选中项时返回 null。 */
export function HistoricalCaseVerificationDetail({ category, batch, item, point, pending, lookup }: {
  category: VerificationCategory
  batch?: VerificationBatchView
  item?: VerificationCaseView
  point?: SupplementalPointView
  pending?: CaseFindingView
  lookup: VerificationLookup
}) {
  if (category === 'cases') return item ? <CaseArchive item={item} lookup={lookup} /> : null
  if (category === 'points') return point ? <SupplementalPointArchive point={point} lookup={lookup} /> : null
  if (category === 'pending') return pending ? <PendingArchive finding={pending} lookup={lookup} /> : null
  return batch ? <RuleVerificationArchive lookup={lookup} batch={batch} /> : null
}
