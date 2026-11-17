import { useState, type ReactNode } from 'react'
import { Empty, Tag } from 'antd'
import {
  ArtifactBreakdown,
  ArtifactDetailTitle,
  ArtifactDivider,
  ArtifactEmpty,
  ArtifactEvidence,
  ArtifactField,
  ArtifactHeader,
  ArtifactKicker,
  ArtifactListRow,
  ArtifactSplit,
  ArtifactStat,
  ArtifactTabs,
} from '@/shared/components/ArtifactView'
import hostStyles from '../styles/artifact-view-host.module.css'
import { cx } from '@/shared/utils/cx'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'

const TABS = [
  { key: 'summary', label: '结论', hint: '评审范围、依据与输入缺口' },
  { key: 'issues', label: '问题', hint: '评审报告仅供人工判断，不阻断材料整理' },
  { key: 'coverage', label: '覆盖度', hint: '结构、质量、气味、行为、追溯与输入审计' },
] as const

type Tab = (typeof TABS)[number]['key']

const STATUS: Record<string, { label: string; color: string; tone: 'ok' | 'warn' | 'danger' }> = {
  passed: { label: '通过', color: 'green', tone: 'ok' },
  needs_clarification: { label: '待澄清', color: 'gold', tone: 'warn' },
  blocked: { label: '阻断', color: 'red', tone: 'danger' },
}

const SEVERITY: Record<string, { label: string; color: string }> = {
  blocker: { label: '阻断', color: 'red' },
  major: { label: '重要', color: 'gold' },
  minor: { label: '次要', color: 'default' },
}

const ISSUE_TYPE: Record<string, string> = {
  conflict: '冲突',
  ambiguity: '歧义',
  missing: '缺失',
  weak_ac: '弱验收标准',
  untestable: '不可测',
  inconsistency: '不一致',
  input_gap: '输入缺口',
}

const OWNER: Record<string, string> = { product: '产品', dev: '开发', qa: '测试' }

const VERIFY_METHOD: Record<string, string> = {
  test: '测试',
  analysis: '分析',
  demonstration: '演示',
  inspection: '检查',
}

const FAILURE_MODE: Record<string, string> = {
  misinterpret: '会被理解错',
  missed_rule: '会漏规则',
  no_oracle: '没有判定依据',
  conflict_escape: '冲突会漏到下游',
}

const STRUCTURE_NAME: Record<string, string> = {
  background: '背景',
  goal: '目标',
  stories: '用户故事',
  features: '功能',
  nfr: '非功能需求',
  boundary: '边界',
  ac: '验收标准',
  kpi: 'KPI',
  dependencies: '依赖',
  timeline: '时间线',
  prototype: '原型',
}

const STRUCTURE_STATUS: Record<string, { label: string; color: string }> = {
  present: { label: '完整', color: 'green' },
  thin: { label: '过薄', color: 'gold' },
  absent: { label: '缺失', color: 'red' },
}

const QUALITY_NAME: Record<string, string> = {
  unambiguous: '无歧义',
  singular: '单一要求',
  complete: '完整',
  verifiable: '可验证',
  necessary: '必要',
  consistent: '一致',
}

const SMELL: Record<string, string> = {
  vague: '模糊',
  optional: '可选但未定义默认',
  subjective: '主观',
  loophole: '漏洞',
  unbounded: '无上限',
  compound: '复合要求',
  tbd: '待定',
}

const BEHAVIOR_AREA: Record<string, string> = {
  state: '状态',
  decision: '判定',
  time: '时间/幂等',
  failure: '失败路径',
  ux: '交互状态',
}

const TRACE_KIND: Record<string, string> = {
  rule_without_ac: '规则缺验收标准',
  ac_without_rule: '验收标准缺规则',
  goal_without_feature: '目标缺功能',
  feature_without_goal: '功能缺目标',
}

const PASS_FAIL: Record<string, { label: string; color: string }> = {
  pass: { label: '通过', color: 'green' },
  fail: { label: '不通过', color: 'red' },
}

const COVERAGE_STATUS: Record<string, { label: string; color: string }> = {
  covered: { label: '已覆盖', color: 'green' },
  gap: { label: '缺口', color: 'gold' },
}

const COVERAGE_ITEMS = [
  { key: 'structure', label: '结构盘点' },
  { key: 'quality', label: '质量特性' },
  { key: 'smells', label: '需求气味' },
  { key: 'behavior', label: '行为完整性' },
  { key: 'trace', label: '追溯' },
  { key: 'audit', label: '输入审计' },
] as const

type CoverageKey = (typeof COVERAGE_ITEMS)[number]['key']

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.map(toDisplayText).filter(Boolean) : []
}

function labelOf(table: Record<string, string>, value: unknown): string {
  const key = toDisplayText(value)
  return table[key] ?? key
}

function SummaryBlock({ title, wide, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return <section className={cx('rounded-[9px] border border-app-surface-border bg-app-surface px-4 py-3.5', wide && 'col-span-full')}>
    <h3 className="mb-2 text-[11.5px] [font-weight:650] text-app-surface-text">{title}</h3>
    {children}
  </section>
}

function TextList({ title, values, wide = false }: { title: string; values: string[]; wide?: boolean }) {
  return <SummaryBlock title={title} wide={wide}>
    {values.length
      ? <ul className="m-0 pl-[18px] text-[11.5px] leading-[1.7] text-app-surface-text [&>li+li]:mt-1">{values.map((value, index) => <li key={`${title}-${index}`}>{value}</li>)}</ul>
      : <p className="m-0 text-[10.5px] text-app-surface-text-muted">未记录</p>}
  </SummaryBlock>
}

function SummaryTab({ summary, status, counts, issueCount, advisory }: {
  summary: Record<string, unknown>
  status: string
  counts: { blocker: number; major: number; minor: number }
  issueCount: number
  advisory: string
}) {
  const meta = STATUS[status]
  return <div className="flex h-full min-h-0 flex-col gap-2.5">
    <ArtifactHeader hint={advisory} hintClassName="max-narrow:hidden">
      <Tag color={meta?.color ?? 'default'}>{meta?.label ?? status}</Tag>
      <ArtifactStat label="问题" value={issueCount} />
      <ArtifactDivider />
      <ArtifactBreakdown items={[
        { label: '阻断', value: counts.blocker, dot: 'danger' },
        { label: '重要', value: counts.major, dot: 'warn' },
        { label: '次要', value: counts.minor, dot: 'muted' },
      ]} />
    </ArtifactHeader>
    <div className="grid min-h-0 flex-1 grid-cols-2 content-start gap-2.5 overflow-auto p-0.5 max-narrow:grid-cols-1 max-narrow:overflow-visible">
      <SummaryBlock title="评审范围" wide>
        <p className="m-0 text-[11.5px] leading-[1.7] text-app-surface-text [overflow-wrap:anywhere]">{toDisplayText(summary.scope) || '未记录'}</p>
      </SummaryBlock>
      <TextList title="已读材料" values={texts(summary.materialsReviewed)} />
      <TextList title="已确认事实" values={texts(summary.confirmedFacts)} />
      <TextList title="工作假设" values={texts(summary.workingAssumptions)} />
      <TextList title="待验证假设" values={texts(summary.hypothesesToVerify)} />
      <TextList title="输入缺口" values={texts(summary.inputGaps)} wide />
    </div>
  </div>
}

function IssuesTab({ issues }: { issues: Record<string, unknown>[] }) {
  const rank: Record<string, number> = { blocker: 0, major: 1, minor: 2 }
  const sorted = [...issues].sort((a, b) => (rank[toDisplayText(a.severity)] ?? 9) - (rank[toDisplayText(b.severity)] ?? 9))
  const [activeId, setActiveId] = useState<string | null>(null)
  const active = sorted.find(issue => toDisplayText(issue.id) === activeId) ?? sorted[0]
  const counts = {
    blocker: issues.filter(issue => issue.severity === 'blocker').length,
    major: issues.filter(issue => issue.severity === 'major').length,
    minor: issues.filter(issue => issue.severity === 'minor').length,
  }

  if (!issues.length) return <ArtifactEmpty description="未发现问题" />

  const evidence = active ? toRecordArray(active.evidence) : []
  const fields = active ? [
    ['影响', toDisplayText(active.impact)],
    ['待确认问题', toDisplayText(active.question)],
    ['建议下一步', toDisplayText(active.nextAction)],
    ['验证方式', labelOf(VERIFY_METHOD, active.verifyMethod)],
    ['失败模式', labelOf(FAILURE_MODE, active.failureMode)],
  ].filter(([, value]) => value) : []

  return <div className="flex h-full min-h-0 flex-col gap-2.5">
    <ArtifactHeader hint="评审报告仅供人工判断，不阻断材料整理" hintClassName="max-narrow:hidden">
      <ArtifactStat label="问题" value={issues.length} />
      <ArtifactDivider />
      <ArtifactBreakdown items={[
        { label: '阻断', value: counts.blocker, dot: 'danger' },
        { label: '重要', value: counts.major, dot: 'warn' },
        { label: '次要', value: counts.minor, dot: 'muted' },
      ]} />
    </ArtifactHeader>
    <ArtifactSplit
      listLabel="评审问题列表"
      detailLabel="评审问题详情"
      list={sorted.map((issue, index) => {
        const severity = toDisplayText(issue.severity)
        const meta = SEVERITY[severity]
        return <ArtifactListRow
          key={toDisplayText(issue.id) || index}
          id={toDisplayText(issue.id) || index + 1}
          title={toDisplayText(issue.topic) || '未命名问题'}
          meta={`${labelOf(ISSUE_TYPE, issue.type)} · ${labelOf(OWNER, issue.suggestedOwner)}`}
          active={active === issue}
          onClick={() => setActiveId(toDisplayText(issue.id))}
          trailing={<Tag color={meta?.color ?? 'default'}>{meta?.label ?? severity}</Tag>}
        />
      })}
      detail={active ? <>
        <ArtifactKicker badge="评审问题">
          <span>{toDisplayText(active.id)}</span>
          <Tag color={SEVERITY[toDisplayText(active.severity)]?.color ?? 'default'}>{SEVERITY[toDisplayText(active.severity)]?.label ?? toDisplayText(active.severity)}</Tag>
          <Tag>{labelOf(ISSUE_TYPE, active.type)}</Tag>
          <Tag>{labelOf(OWNER, active.suggestedOwner)}</Tag>
        </ArtifactKicker>
        <ArtifactDetailTitle>{toDisplayText(active.topic) || '未命名问题'}</ArtifactDetailTitle>
        {evidence.length ? <ArtifactEvidence title="证据" count={evidence.length} className="mt-4">
          {evidence.map((item, index) => <blockquote key={index} className="m-0 rounded-[6px] border border-app-surface-border border-l-2 border-l-app-accent bg-app-surface-hover px-[10px] py-[9px]">
            <p className="m-0 text-[11.5px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">“{toDisplayText(item.quote)}”</p>
            <cite className="mt-1 block text-[10px] not-italic text-app-surface-text-muted">{toDisplayText(item.sourceName)}{toDisplayText(item.locator) ? ` · ${toDisplayText(item.locator)}` : ''}</cite>
          </blockquote>)}
        </ArtifactEvidence> : null}
        <div className="mt-4 flex flex-col gap-2.5">
          {fields.map(([label, value]) => <ArtifactField
            key={label}
            label={label}
            value={value}
            labelWidth="md"
            tone={label === '待确认问题' ? 'question' : 'default'}
            className="mt-0"
          />)}
        </div>
      </> : null}
    />
  </div>
}

function CoverageRow({ name, tail, quote, note }: { name: ReactNode; tail?: ReactNode; quote?: ReactNode; note?: ReactNode }) {
  return <div className="flex flex-wrap items-baseline gap-2 border-b border-app-surface-border py-[9px] last:border-b-0">
    <span className="flex-[0_0_120px] text-[11.5px] font-semibold text-app-surface-text">{name}</span>
    {tail ? <span className="inline-flex flex-wrap items-center gap-2 [&_.ant-tag]:m-0 [&_.ant-tag]:px-[5px] [&_.ant-tag]:text-[9px] [&_.ant-tag]:leading-4">{tail}</span> : null}
    {quote ? <span className="flex-[1_1_260px] text-[10.5px] text-app-surface-text [overflow-wrap:anywhere]">{quote}</span> : null}
    {note ? <span className="flex-[1_1_260px] text-[10.5px] leading-[1.6] text-app-surface-text-muted [overflow-wrap:anywhere]">{note}</span> : null}
  </div>
}

function CoverageTab({ coverage }: { coverage: Record<string, unknown> }) {
  const structure = toRecordArray(coverage.structure)
  const quality = toRecordArray(coverage.qualityCharacteristics)
  const smells = toRecordArray(coverage.smells)
  const behavior = toRecordArray(coverage.behavioralStates)
  const trace = toRecordArray(coverage.traceability)
  const audit = toRecord(coverage.inputAudit) ?? {}
  const missing = texts(audit.missing)

  const dims = [
    { key: 'structure' as const, label: '结构盘点', count: structure.length, attention: structure.filter(row => toDisplayText(row.status) !== 'present').length },
    { key: 'quality' as const, label: '质量特性', count: quality.length, attention: quality.filter(row => toDisplayText(row.status) === 'fail').length },
    { key: 'smells' as const, label: '需求气味', count: smells.length, attention: smells.length },
    { key: 'behavior' as const, label: '行为完整性', count: behavior.length, attention: behavior.filter(row => toDisplayText(row.status) === 'gap').length },
    { key: 'trace' as const, label: '追溯', count: trace.length, attention: trace.filter(row => toDisplayText(row.status) === 'fail').length },
    { key: 'audit' as const, label: '输入审计', count: 0, attention: missing.length },
  ]
  const attentionTotal = dims.reduce((sum, dim) => sum + dim.attention, 0)
  const [activeKey, setActiveKey] = useState<CoverageKey>('structure')
  const active = dims.find(dim => dim.key === activeKey) ?? dims[0]

  const renderDetail = () => {
    if (active.key === 'structure') return <>
      <ArtifactKicker badge="覆盖度"><span>结构盘点</span></ArtifactKicker>
      <ArtifactDetailTitle count={structure.length}>结构盘点</ArtifactDetailTitle>
      <div className="mt-3.5 flex flex-col">
        {structure.map((row, index) => <CoverageRow
          key={index}
          name={labelOf(STRUCTURE_NAME, row.name)}
          tail={<Tag color={STRUCTURE_STATUS[toDisplayText(row.status)]?.color ?? 'default'}>{STRUCTURE_STATUS[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>}
        />)}
      </div>
    </>
    if (active.key === 'quality') return <>
      <ArtifactKicker badge="覆盖度"><span>质量特性</span></ArtifactKicker>
      <ArtifactDetailTitle count={quality.length}>质量特性</ArtifactDetailTitle>
      <div className="mt-3.5 flex flex-col">
        {quality.map((row, index) => <CoverageRow
          key={index}
          name={labelOf(QUALITY_NAME, row.name)}
          tail={<>
            <Tag color={PASS_FAIL[toDisplayText(row.status)]?.color ?? 'default'}>{PASS_FAIL[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>
            {Array.isArray(row.issueIds) && row.issueIds.length ? <em className="not-italic text-[10.5px] text-app-surface-text-muted">{row.issueIds.map(toDisplayText).join('、')}</em> : null}
          </>}
        />)}
      </div>
    </>
    if (active.key === 'smells') return <>
      <ArtifactKicker badge="覆盖度"><span>需求气味</span></ArtifactKicker>
      <ArtifactDetailTitle count={smells.length}>需求气味</ArtifactDetailTitle>
      <div className="mt-3.5 flex flex-col">
        {smells.map((row, index) => <CoverageRow
          key={index}
          name={labelOf(SMELL, row.type)}
          quote={`“${toDisplayText(row.quote)}”`}
          tail={<em className="not-italic text-[10.5px] text-app-surface-text-muted">{toDisplayText(row.issueId)}</em>}
        />)}
      </div>
    </>
    if (active.key === 'behavior') return <>
      <ArtifactKicker badge="覆盖度"><span>行为完整性</span></ArtifactKicker>
      <ArtifactDetailTitle count={behavior.length}>行为完整性</ArtifactDetailTitle>
      <div className="mt-3.5 flex flex-col">
        {behavior.map((row, index) => <CoverageRow
          key={index}
          name={labelOf(BEHAVIOR_AREA, row.area)}
          tail={<Tag color={COVERAGE_STATUS[toDisplayText(row.status)]?.color ?? 'default'}>{COVERAGE_STATUS[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>}
          note={toDisplayText(row.note)}
        />)}
      </div>
    </>
    if (active.key === 'trace') return <>
      <ArtifactKicker badge="覆盖度"><span>追溯</span></ArtifactKicker>
      <ArtifactDetailTitle count={trace.length}>追溯</ArtifactDetailTitle>
      <div className="mt-3.5 flex flex-col">
        {trace.map((row, index) => <CoverageRow
          key={index}
          name={labelOf(TRACE_KIND, row.kind)}
          tail={<>
            <Tag color={PASS_FAIL[toDisplayText(row.status)]?.color ?? 'default'}>{PASS_FAIL[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>
            {toDisplayText(row.issueId) ? <em className="not-italic text-[10.5px] text-app-surface-text-muted">{toDisplayText(row.issueId)}</em> : null}
          </>}
          note={toDisplayText(row.note)}
        />)}
      </div>
    </>
    return <>
      <ArtifactKicker badge="覆盖度"><span>输入审计</span></ArtifactKicker>
      <ArtifactDetailTitle count={missing.length}>输入审计</ArtifactDetailTitle>
      <div className="mt-3.5 grid grid-cols-2 gap-2.5 max-narrow:grid-cols-1">
        <TextList title="已提供材料" values={texts(audit.materials)} />
        <TextList title="缺失材料" values={missing} />
        <SummaryBlock title="时效性"><p className="m-0 text-[11.5px] leading-[1.7] text-app-surface-text">{toDisplayText(audit.recency) || '未记录'}</p></SummaryBlock>
        <SummaryBlock title="可比性"><p className="m-0 text-[11.5px] leading-[1.7] text-app-surface-text">{toDisplayText(audit.comparability) || '未记录'}</p></SummaryBlock>
      </div>
    </>
  }

  return <div className="flex h-full min-h-0 flex-col gap-2.5">
    <ArtifactHeader hint="结构、质量、气味、行为、追溯与输入审计" hintClassName="max-narrow:hidden">
      <ArtifactStat label="覆盖度" value={dims.length} />
      <ArtifactDivider />
      <ArtifactBreakdown items={[{ label: '关注项', value: <strong className="[font-weight:650] text-app-status-warning-text">{attentionTotal}</strong> }]} />
    </ArtifactHeader>
    <ArtifactSplit
      listLabel="覆盖度维度列表"
      detailLabel="覆盖度详情"
      list={dims.map((dim) => <ArtifactListRow
        key={dim.key}
        title={dim.label}
        meta={dim.key === 'audit' ? `缺失 ${dim.attention} 项` : `${dim.count} 项`}
        active={dim.key === active.key}
        onClick={() => setActiveKey(dim.key)}
        trailing={dim.attention ? <Tag color="gold">关注 {dim.attention}</Tag> : <Tag color="green">完整</Tag>}
      />)}
      detail={renderDetail()}
    />
  </div>
}

export function RequirementReviewView({ content }: { content: string }) {
  const [tab, setTab] = useState<Tab>('summary')
  let artifact: Record<string, unknown>
  try {
    const parsed = JSON.parse(content)
    const record = toRecord(parsed)
    if (!record || record.artifactType !== 'requirement_review') throw new Error('not a review')
    artifact = record
  } catch {
    return <Empty description="评审报告格式无效，请重新生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }
  const summary = toRecord(artifact.summary) ?? {}
  const coverage = toRecord(artifact.coverage) ?? {}
  const issues = toRecordArray(artifact.issues)
  const status = toDisplayText(artifact.reviewStatus)
  const statusMeta = STATUS[status]
  const counts = {
    blocker: issues.filter(issue => issue.severity === 'blocker').length,
    major: issues.filter(issue => issue.severity === 'major').length,
    minor: issues.filter(issue => issue.severity === 'minor').length,
  }
  const currentTab = TABS.find(item => item.key === tab)!
  const tabCounts: Record<Tab, number | null> = {
    summary: null,
    issues: issues.length,
    coverage: COVERAGE_ITEMS.length,
  }

  return <div className={cx('flex min-h-0 flex-1 flex-col bg-app-surface', hostStyles.requirementReviewRoot)}>
    <ArtifactTabs
      ariaLabel="需求评审"
      active={tab}
      onChange={setTab}
      tabs={TABS.map(item => ({
        key: item.key,
        label: item.label,
        dot: item.key === 'summary' ? (statusMeta?.tone ?? 'warn') : undefined,
        count: item.key === 'summary' ? undefined : tabCounts[item.key],
        tone: item.key === 'issues' && tabCounts[item.key] ? (counts.blocker ? 'danger' : 'warn') : undefined,
      }))}
    />
    <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-2.5 max-narrow:overflow-auto" role="tabpanel" aria-label={currentTab.label}>
      {tab === 'summary' ? <SummaryTab summary={summary} status={status} counts={counts} issueCount={issues.length} advisory="评审报告仅供人工判断，不阻断材料整理" /> : null}
      {tab === 'issues' ? <IssuesTab issues={issues} /> : null}
      {tab === 'coverage' ? <CoverageTab coverage={coverage} /> : null}
    </div>
  </div>
}
