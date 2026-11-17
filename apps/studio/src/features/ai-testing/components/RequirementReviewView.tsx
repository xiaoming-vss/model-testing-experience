import { useState } from 'react'
import { Empty, Tag } from 'antd'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import '../styles/requirement-review.css'

const TABS = [
  { key: 'summary', label: '结论', hint: '评审范围、依据与输入缺口' },
  { key: 'issues', label: '问题', hint: '评审报告仅供人工判断，不阻断材料整理' },
  { key: 'coverage', label: '覆盖度', hint: '结构、质量、气味、行为、追溯与输入审计' },
] as const

type Tab = (typeof TABS)[number]['key']

const STATUS: Record<string, { label: string; color: string; tone: string }> = {
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

function TextList({ title, values, wide = false }: { title: string; values: string[]; wide?: boolean }) {
  return <section className={`ai-rr-summary-block${wide ? ' is-wide' : ''}`}>
    <h3>{title}</h3>
    {values.length
      ? <ul>{values.map((value, index) => <li key={`${title}-${index}`}>{value}</li>)}</ul>
      : <p className="ai-rr-muted">未记录</p>}
  </section>
}

function SummaryTab({ summary, status, counts, issueCount, advisory }: {
  summary: Record<string, unknown>
  status: string
  counts: { blocker: number; major: number; minor: number }
  issueCount: number
  advisory: string
}) {
  const meta = STATUS[status]
  return <div className="ai-rr-summary">
    <header className="ai-rr-head">
      <Tag color={meta?.color ?? 'default'}>{meta?.label ?? status}</Tag>
      <div className="ai-rr-stat"><span>问题</span><strong>{issueCount}</strong></div>
      <span className="ai-rr-divider" aria-hidden="true" />
      <div className="ai-rr-severity">
        <span><i className="ai-rr-dot is-danger" aria-hidden="true" />阻断 {counts.blocker}</span>
        <span><i className="ai-rr-dot is-warn" aria-hidden="true" />重要 {counts.major}</span>
        <span><i className="ai-rr-dot is-muted" aria-hidden="true" />次要 {counts.minor}</span>
      </div>
      <span className="ai-rr-hint">{advisory}</span>
    </header>
    <div className="ai-rr-summary-grid">
      <section className="ai-rr-summary-block is-wide">
        <h3>评审范围</h3>
        <p>{toDisplayText(summary.scope) || '未记录'}</p>
      </section>
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

  if (!issues.length) return <div className="ai-rr-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未发现问题" /></div>

  const evidence = active ? toRecordArray(active.evidence) : []
  const fields = active ? [
    ['影响', toDisplayText(active.impact)],
    ['待确认问题', toDisplayText(active.question)],
    ['建议下一步', toDisplayText(active.nextAction)],
    ['验证方式', labelOf(VERIFY_METHOD, active.verifyMethod)],
    ['失败模式', labelOf(FAILURE_MODE, active.failureMode)],
  ].filter(([, value]) => value) : []

  return <div className="ai-rr-issues">
    <header className="ai-rr-head">
      <div className="ai-rr-stat"><span>问题</span><strong>{issues.length}</strong></div>
      <span className="ai-rr-divider" aria-hidden="true" />
      <div className="ai-rr-severity">
        <span><i className="ai-rr-dot is-danger" aria-hidden="true" />阻断 {counts.blocker}</span>
        <span><i className="ai-rr-dot is-warn" aria-hidden="true" />重要 {counts.major}</span>
        <span><i className="ai-rr-dot is-muted" aria-hidden="true" />次要 {counts.minor}</span>
      </div>
      <span className="ai-rr-hint">评审报告仅供人工判断，不阻断材料整理</span>
    </header>
    <div className="ai-rr-split">
      <aside className="ai-rr-list" aria-label="评审问题列表">
        {sorted.map((issue, index) => {
          const severity = toDisplayText(issue.severity)
          const meta = SEVERITY[severity]
          return <button
            type="button"
            key={toDisplayText(issue.id) || index}
            className={`ai-rr-row${active === issue ? ' is-active' : ''}`}
            onClick={() => setActiveId(toDisplayText(issue.id))}
          >
            <span className="ai-rr-row-id">{toDisplayText(issue.id) || index + 1}</span>
            <span className="ai-rr-row-main">
              <span className="ai-rr-row-title">{toDisplayText(issue.topic) || '未命名问题'}</span>
              <span className="ai-rr-row-meta">{labelOf(ISSUE_TYPE, issue.type)} · {labelOf(OWNER, issue.suggestedOwner)}</span>
            </span>
            <Tag color={meta?.color ?? 'default'}>{meta?.label ?? severity}</Tag>
          </button>
        })}
      </aside>
      <section className="ai-rr-detail" aria-label="评审问题详情">
        {active ? <>
          <div className="ai-rr-kicker">
            <span className="ai-rr-badge">评审问题</span>
            <span>{toDisplayText(active.id)}</span>
            <Tag color={SEVERITY[toDisplayText(active.severity)]?.color ?? 'default'}>{SEVERITY[toDisplayText(active.severity)]?.label ?? toDisplayText(active.severity)}</Tag>
            <Tag>{labelOf(ISSUE_TYPE, active.type)}</Tag>
            <Tag>{labelOf(OWNER, active.suggestedOwner)}</Tag>
          </div>
          <h2>{toDisplayText(active.topic) || '未命名问题'}</h2>
          {evidence.length ? <section className="ai-rr-evidence">
            <h4>证据<span>{evidence.length}</span></h4>
            <div className="ai-rr-evidence-list">
              {evidence.map((item, index) => <blockquote key={index}>
                <p>“{toDisplayText(item.quote)}”</p>
                <cite>{toDisplayText(item.sourceName)}{toDisplayText(item.locator) ? ` · ${toDisplayText(item.locator)}` : ''}</cite>
              </blockquote>)}
            </div>
          </section> : null}
          <div className="ai-rr-fields">
            {fields.map(([label, value]) => <div className={`ai-rr-field${label === '待确认问题' ? ' is-question' : ''}`} key={label}>
              <span>{label}</span>
              <p>{value}</p>
            </div>)}
          </div>
        </> : null}
      </section>
    </div>
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
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>结构盘点</span></div>
      <h2>结构盘点<span className="ai-rr-title-count">{structure.length}</span></h2>
      <div className="ai-rr-coverage-list">
        {structure.map((row, index) => <div className="ai-rr-coverage-row" key={index}>
          <span className="ai-rr-coverage-name">{labelOf(STRUCTURE_NAME, row.name)}</span>
          <span className="ai-rr-coverage-tail"><Tag color={STRUCTURE_STATUS[toDisplayText(row.status)]?.color ?? 'default'}>{STRUCTURE_STATUS[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag></span>
        </div>)}
      </div>
    </>
    if (active.key === 'quality') return <>
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>质量特性</span></div>
      <h2>质量特性<span className="ai-rr-title-count">{quality.length}</span></h2>
      <div className="ai-rr-coverage-list">
        {quality.map((row, index) => <div className="ai-rr-coverage-row" key={index}>
          <span className="ai-rr-coverage-name">{labelOf(QUALITY_NAME, row.name)}</span>
          <span className="ai-rr-coverage-tail">
            <Tag color={PASS_FAIL[toDisplayText(row.status)]?.color ?? 'default'}>{PASS_FAIL[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>
            {Array.isArray(row.issueIds) && row.issueIds.length ? <em>{row.issueIds.map(toDisplayText).join('、')}</em> : null}
          </span>
        </div>)}
      </div>
    </>
    if (active.key === 'smells') return <>
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>需求气味</span></div>
      <h2>需求气味<span className="ai-rr-title-count">{smells.length}</span></h2>
      <div className="ai-rr-coverage-list">
        {smells.map((row, index) => <div className="ai-rr-coverage-row" key={index}>
          <span className="ai-rr-coverage-name">{labelOf(SMELL, row.type)}</span>
          <span className="ai-rr-coverage-quote">“{toDisplayText(row.quote)}”</span>
          <span className="ai-rr-coverage-tail"><em>{toDisplayText(row.issueId)}</em></span>
        </div>)}
      </div>
    </>
    if (active.key === 'behavior') return <>
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>行为完整性</span></div>
      <h2>行为完整性<span className="ai-rr-title-count">{behavior.length}</span></h2>
      <div className="ai-rr-coverage-list">
        {behavior.map((row, index) => <div className="ai-rr-coverage-row" key={index}>
          <span className="ai-rr-coverage-name">{labelOf(BEHAVIOR_AREA, row.area)}</span>
          <span className="ai-rr-coverage-tail"><Tag color={COVERAGE_STATUS[toDisplayText(row.status)]?.color ?? 'default'}>{COVERAGE_STATUS[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag></span>
          <span className="ai-rr-coverage-note">{toDisplayText(row.note)}</span>
        </div>)}
      </div>
    </>
    if (active.key === 'trace') return <>
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>追溯</span></div>
      <h2>追溯<span className="ai-rr-title-count">{trace.length}</span></h2>
      <div className="ai-rr-coverage-list">
        {trace.map((row, index) => <div className="ai-rr-coverage-row" key={index}>
          <span className="ai-rr-coverage-name">{labelOf(TRACE_KIND, row.kind)}</span>
          <span className="ai-rr-coverage-tail">
            <Tag color={PASS_FAIL[toDisplayText(row.status)]?.color ?? 'default'}>{PASS_FAIL[toDisplayText(row.status)]?.label ?? toDisplayText(row.status)}</Tag>
            {toDisplayText(row.issueId) ? <em>{toDisplayText(row.issueId)}</em> : null}
          </span>
          <span className="ai-rr-coverage-note">{toDisplayText(row.note)}</span>
        </div>)}
      </div>
    </>
    return <>
      <div className="ai-rr-kicker"><span className="ai-rr-badge">覆盖度</span><span>输入审计</span></div>
      <h2>输入审计<span className="ai-rr-title-count">{missing.length}</span></h2>
      <div className="ai-rr-audit">
        <TextList title="已提供材料" values={texts(audit.materials)} />
        <TextList title="缺失材料" values={missing} />
        <section className="ai-rr-summary-block"><h3>时效性</h3><p>{toDisplayText(audit.recency) || '未记录'}</p></section>
        <section className="ai-rr-summary-block"><h3>可比性</h3><p>{toDisplayText(audit.comparability) || '未记录'}</p></section>
      </div>
    </>
  }

  return <div className="ai-rr-coverage">
    <header className="ai-rr-head">
      <div className="ai-rr-stat"><span>覆盖度</span><strong>{dims.length}</strong></div>
      <span className="ai-rr-divider" aria-hidden="true" />
      <div className="ai-rr-related"><span>关注项 <strong className="is-warn">{attentionTotal}</strong></span></div>
      <span className="ai-rr-hint">结构、质量、气味、行为、追溯与输入审计</span>
    </header>
    <div className="ai-rr-split">
      <aside className="ai-rr-list" aria-label="覆盖度维度列表">
        {dims.map((dim) => <button
          type="button"
          key={dim.key}
          className={`ai-rr-row${dim.key === active.key ? ' is-active' : ''}`}
          onClick={() => setActiveKey(dim.key)}
        >
          <span className="ai-rr-row-main">
            <span className="ai-rr-row-title">{dim.label}</span>
            <span className="ai-rr-row-meta">{dim.key === 'audit' ? `缺失 ${dim.attention} 项` : `${dim.count} 项`}</span>
          </span>
          {dim.attention ? <Tag color="gold">关注 {dim.attention}</Tag> : <Tag color="green">完整</Tag>}
        </button>)}
      </aside>
      <section className="ai-rr-detail" aria-label="覆盖度详情">{renderDetail()}</section>
    </div>
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

  return <div className="ai-rr">
    <div className="ai-rr-tabs" role="tablist" aria-label="需求评审">
      {TABS.map((item) => <button
        key={item.key}
        type="button"
        role="tab"
        aria-selected={tab === item.key}
        className={`ai-rr-tab${tab === item.key ? ' is-active' : ''}`}
        onClick={() => setTab(item.key)}
      >
        {item.label}
        {item.key === 'summary'
          ? <span className={`ai-rr-status-dot is-${statusMeta?.tone ?? 'warn'}`} title={statusMeta?.label ?? status} />
          : <span className={`ai-rr-count${item.key === 'issues' && tabCounts[item.key] ? (counts.blocker ? ' is-danger' : ' is-warn') : ''}`}>{tabCounts[item.key]}</span>}
      </button>)}
    </div>
    <div className="ai-rr-page" role="tabpanel" aria-label={currentTab.label}>
      {tab === 'summary' ? <SummaryTab summary={summary} status={status} counts={counts} issueCount={issues.length} advisory="评审报告仅供人工判断，不阻断材料整理" /> : null}
      {tab === 'issues' ? <IssuesTab issues={issues} /> : null}
      {tab === 'coverage' ? <CoverageTab coverage={coverage} /> : null}
    </div>
  </div>
}
