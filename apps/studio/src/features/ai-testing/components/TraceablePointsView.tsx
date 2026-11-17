import { useCallback, useMemo, useState } from 'react'
import { Empty, Input, Tag } from 'antd'
import { CaseNameTreeView } from './CaseNamesResultView'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { buildCaseNameTree, type CaseNameTreeNode } from '../utils/caseNameTree'
import '@/features/ai-testing/styles/traceable-points.css'

type Props = {
  content: string
  onChange?: (content: string) => void
  materialContent?: string
  rootTitle?: string
  expanded?: boolean
}

type PointEntry = { id: string; point: Record<string, unknown> }
type GapEntry = { id: string; gap: Record<string, unknown>; relatedPointIds: string[] }

const REF_FIELDS = [
  { field: 'materialBlockIds', label: '材料块' },
  { field: 'testObjectIds', label: '测试对象' },
  { field: 'impactAreaIds', label: '影响范围' },
  { field: 'riskIds', label: '风险' },
  { field: 'materialQuestionIds', label: '材料问题' },
  { field: 'scopeQuestionIds', label: '分析问题' },
] as const

type RefField = (typeof REF_FIELDS)[number]['field']

function refValues(record: Record<string, unknown>, field: RefField) {
  return Array.isArray(record[field]) ? record[field].map(toDisplayText).filter(Boolean) : []
}

function totalRefCount(point: Record<string, unknown>) {
  return REF_FIELDS.reduce((sum, item) => sum + refValues(point, item.field).length, 0)
}

function collectPointIds(node: CaseNameTreeNode): string[] {
  if (node.kind === 'point') return [node.id]
  return node.children.flatMap(collectPointIds)
}

function aggregateRefs(entries: PointEntry[]) {
  const result = {} as Record<RefField, string[]>
  REF_FIELDS.forEach(({ field }) => {
    const values = new Set<string>()
    entries.forEach(({ point }) => refValues(point, field).forEach(value => values.add(value)))
    result[field] = [...values]
  })
  return result
}

function EvidenceList({ blockIds, blockById, sourceById }: {
  blockIds: string[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  return <div className="ai-tp-relations-evidence-list">
    {blockIds.map((id) => {
      const block = blockById.get(id)
      if (!block) return null
      const source = sourceById.get(toDisplayText(block.sourceId))
      return <div className="ai-tp-relations-evidence" key={id}>
        <div className="ai-tp-relations-evidence-head">
          <strong>{toDisplayText(source?.name) || '来源未找到'}</strong>
          <span>{toDisplayText(block.locator)}</span>
        </div>
        <MaterialBlockContent block={block as MaterialBlock} />
      </div>
    })}
  </div>
}

function PointRelations({ entry, blockById, sourceById, onRename }: {
  entry: PointEntry
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
  onRename?: (id: string, name: string) => void
}) {
  const { id, point } = entry
  const name = toDisplayText(point.name) || id
  const context = [toDisplayText(point.module), toDisplayText(point.dimension)].filter(Boolean).join(' / ')
  const groups = REF_FIELDS.map(item => ({ ...item, values: refValues(point, item.field) }))
  const hasRefs = groups.some(group => group.values.length > 0)

  return <div className="ai-tp-relations">
    <header className="ai-tp-relations-head">
      <div className="ai-tp-relations-kicker">
        <span className="ai-tp-relations-badge">测试点</span>
        <span>{context || '未分组'}</span>
      </div>
      <strong>{id} {name}</strong>
    </header>
    {onRename ? <label className="ai-tp-relations-rename">
      <span>名称</span>
      <Input
        key={`${id}-${name}`}
        size="small"
        defaultValue={name}
        aria-label={`测试点 ${id}`}
        onBlur={event => {
          const next = event.currentTarget.value.trim()
          if (next && next !== name) onRename(id, next)
        }}
        onPressEnter={event => event.currentTarget.blur()}
      />
      <em>修改后审查状态会重置为自审</em>
    </label> : null}
    {hasRefs ? groups.map(group => group.values.length > 0 ? <section className="ai-tp-relations-group" key={group.field}>
      <h4>{group.label}<span>{group.values.length}</span></h4>
      {group.field === 'materialBlockIds'
        ? <EvidenceList blockIds={group.values} blockById={blockById} sourceById={sourceById} />
        : <div className="ai-tp-relations-chips">{group.values.map(value => <span key={value}>{value}</span>)}</div>}
    </section> : null) : <div className="ai-tp-relations-empty">暂无关联依据</div>}
    <footer className="ai-tp-relations-foot">引用来自冻结的材料与测试范围分析。</footer>
  </div>
}

function GroupRelations({ node, entries, blockById, sourceById }: {
  node: CaseNameTreeNode
  entries: PointEntry[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  const refs = aggregateRefs(entries)
  return <div className="ai-tp-relations">
    <header className="ai-tp-relations-head">
      <div className="ai-tp-relations-kicker">
        <span className="ai-tp-relations-badge is-group">{node.kind === 'root' ? '全部测试点' : '分组'}</span>
      </div>
      <strong>{node.title}</strong>
      <small>{entries.length} 个测试点 · {refs.materialBlockIds.length} 个材料块 · {refs.riskIds.length} 个风险</small>
    </header>
    <section className="ai-tp-relations-group">
      <h4>包含的测试点<span>{entries.length}</span></h4>
      {entries.length ? <ul className="ai-tp-relations-points">
        {entries.map(({ id, point }) => <li key={id}>
          <span>{id}</span>
          <span>{toDisplayText(point.name) || id}</span>
          <em>{totalRefCount(point)} 项</em>
        </li>)}
      </ul> : <div className="ai-tp-relations-empty">暂无测试点</div>}
    </section>
    {refs.materialBlockIds.length ? <section className="ai-tp-relations-group">
      <h4>聚合材料块<span>{refs.materialBlockIds.length}</span></h4>
      <EvidenceList blockIds={refs.materialBlockIds} blockById={blockById} sourceById={sourceById} />
    </section> : null}
    {refs.riskIds.length ? <section className="ai-tp-relations-group">
      <h4>涉及风险<span>{refs.riskIds.length}</span></h4>
      <div className="ai-tp-relations-chips">{refs.riskIds.map(value => <span key={value}>{value}</span>)}</div>
    </section> : null}
    <footer className="ai-tp-relations-foot">分组关联会聚合其下全部测试点的依据。</footer>
  </div>
}

function GapReferenceGroups({ gap, blockById, sourceById }: {
  gap: Record<string, unknown>
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  const groups = REF_FIELDS
    .map(item => ({ ...item, values: refValues(gap, item.field) }))
    .filter(group => group.values.length > 0)
  if (!groups.length) return <div className="ai-tp-review-empty-refs">暂无关联依据</div>
  return <div className="ai-tp-gap-refs">
    {groups.map(group => <section className="ai-tp-gap-ref-group" key={group.field}>
      <h4>{group.label}<span>{group.values.length}</span></h4>
      {group.field === 'materialBlockIds'
        ? <EvidenceList blockIds={group.values} blockById={blockById} sourceById={sourceById} />
        : <div className="ai-tp-relations-chips">{group.values.map(value => <span key={value}>{value}</span>)}</div>}
    </section>)}
  </div>
}

function TraceableIssuesReview({ issues, reviewStatus, reviewLabel }: {
  issues: Record<string, unknown>[]
  reviewStatus: string
  reviewLabel: string
}) {
  const [activeIndex, setActiveIndex] = useState(0)
  const safeIndex = Math.min(activeIndex, Math.max(issues.length - 1, 0))
  const activeIssue = issues[safeIndex]
  const targetId = activeIssue ? toDisplayText(activeIssue.targetId) || '遗漏项' : ''
  const issueText = activeIssue ? toDisplayText(activeIssue.issue) || '未记录问题描述' : ''
  const suggestion = activeIssue ? toDisplayText(activeIssue.suggestion) : ''

  return <div className="ai-tp-issues">
    <header className="ai-tp-review-head">
      <div className="ai-tp-review-stat">
        <span>未解决审查问题</span>
        <strong className={issues.length ? 'is-danger' : 'is-ok'}>{issues.length}</strong>
        <Tag color={issues.length ? 'orange' : reviewStatus === 'independent_reviewed' ? 'green' : 'orange'}>{reviewLabel}</Tag>
      </div>
    </header>
    {issues.length ? <div className="ai-tp-review-split">
      <aside className="ai-tp-review-list" aria-label="未解决的审查问题列表">
        {issues.map((issue, index) => <button
          key={index}
          type="button"
          className={`ai-tp-issue-row${index === safeIndex ? ' is-active' : ''}`}
          onClick={() => setActiveIndex(index)}
        >
          <span className="ai-tp-issue-row-id">{toDisplayText(issue.targetId) || '遗漏项'}</span>
          <span className="ai-tp-issue-row-title">{toDisplayText(issue.issue) || '未记录问题描述'}</span>
        </button>)}
      </aside>
      <section className="ai-tp-review-detail" aria-label="审查问题详情">
        <div className="ai-tp-review-detail-kicker">
          <span className="ai-tp-review-badge is-issue">审查问题</span>
          <span>{targetId}</span>
        </div>
        <h2>{issueText}</h2>
        {suggestion
          ? <div className="ai-tp-review-suggestion"><strong>建议</strong><span>{suggestion}</span></div>
          : <div className="ai-tp-review-empty-refs">暂无修改建议</div>}
      </section>
    </div> : <div className="ai-tp-review-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={reviewStatus === 'independent_reviewed' ? '独立审查通过，没有未解决的审查问题' : '没有未解决的审查问题'} /></div>}
  </div>
}

function TraceableGapsReview({ gaps, activeGap, pointById, blockById, sourceById, onSelectGap, onLocate }: {
  gaps: GapEntry[]
  activeGap?: GapEntry
  pointById: Map<string, PointEntry>
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
  onSelectGap: (id: string) => void
  onLocate: (gap: GapEntry) => void
}) {
  const relatedPoints = activeGap
    ? activeGap.relatedPointIds.map(id => pointById.get(id)).filter((entry): entry is PointEntry => Boolean(entry))
    : []
  const activeDescription = activeGap ? toDisplayText(activeGap.gap.description) || '未命名覆盖缺口' : ''
  const blockedCoverage = activeGap ? toDisplayText(activeGap.gap.blockedCoverage) || '未记录阻塞范围' : ''
  const relatedPointCount = new Set(gaps.flatMap(gap => gap.relatedPointIds)).size

  return <div className="ai-tp-review">
    <header className="ai-tp-review-head">
      <div className="ai-tp-review-stat">
        <span>覆盖缺口</span>
        <strong className={gaps.length ? 'is-warn' : 'is-ok'}>{gaps.length}</strong>
      </div>
      <span className="ai-tp-review-divider" aria-hidden="true" />
      <div className="ai-tp-review-stat">
        <span>关联测试点</span>
        <strong>{relatedPointCount}</strong>
      </div>
    </header>
    {gaps.length ? <div className="ai-tp-review-split">
      <aside className="ai-tp-review-list" aria-label="覆盖缺口列表">
        {gaps.map(gap => <button
          key={gap.id}
          type="button"
          className={`ai-tp-gap-row${gap.id === activeGap?.id ? ' is-active' : ''}`}
          onClick={() => onSelectGap(gap.id)}
        >
          <span className="ai-tp-gap-row-id">{gap.id}</span>
          <span className="ai-tp-gap-row-title">{toDisplayText(gap.gap.description) || '未命名覆盖缺口'}</span>
        </button>)}
      </aside>
      <section className="ai-tp-review-detail" aria-label="覆盖缺口详情">
        {activeGap ? <>
          <div className="ai-tp-review-detail-kicker">
            <span className="ai-tp-review-badge">覆盖缺口</span>
            <span>{activeGap.id}</span>
          </div>
          <h2>{activeDescription}</h2>
          <div className="ai-tp-review-blocked">
            <strong>暂缓覆盖</strong>
            <span>{blockedCoverage}</span>
          </div>
          <GapReferenceGroups gap={activeGap.gap} blockById={blockById} sourceById={sourceById} />
          {relatedPoints.length ? <section className="ai-tp-related-points">
            <div className="ai-tp-related-head">
              <h4>关联测试点<span>{relatedPoints.length}</span></h4>
              <button type="button" className="ai-tp-locate" onClick={() => onLocate(activeGap)}>在树图中查看</button>
            </div>
            <div className="ai-tp-related-list">
              {relatedPoints.map(entry => <span key={entry.id}>{entry.id} {toDisplayText(entry.point.name) || entry.id}</span>)}
            </div>
          </section> : null}
        </> : null}
      </section>
    </div> : <div className="ai-tp-review-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未记录覆盖缺口" /></div>}
  </div>
}

export function TraceablePointsView({ content, onChange, materialContent, rootTitle = '测试点', expanded = true }: Props) {
  const [page, setPage] = useState<'points' | 'issues' | 'gaps'>('points')
  const [activeGapId, setActiveGapId] = useState<string | null>(null)
  const [revealSceneIds, setRevealSceneIds] = useState<string[]>([])
  const [highlightedPointIds, setHighlightedPointIds] = useState<string[]>([])

  const data = useMemo(() => {
    let artifact: Record<string, unknown> | undefined
    let material: Record<string, unknown> | undefined
    try { artifact = toRecord(JSON.parse(content)) ?? undefined } catch { artifact = undefined }
    try { material = toRecord(JSON.parse(materialContent || '')) ?? undefined } catch { material = undefined }
    return {
      artifact,
      points: toRecordArray(artifact?.testPoints),
      gaps: toRecordArray(artifact?.coverageGaps),
      issues: toRecordArray(artifact?.reviewIssues),
      blocks: toRecordArray(material?.materialBlocks),
      sources: toRecordArray(material?.sources),
    }
  }, [content, materialContent])

  const pointEntries = useMemo<PointEntry[]>(() => data.points.map((point, index) => ({
    id: toDisplayText(point.id) || `point-${index}`,
    point,
  })), [data.points])
  const entriesById = useMemo(() => new Map(pointEntries.map(entry => [entry.id, entry])), [pointEntries])
  const blockById = useMemo(() => new Map(data.blocks.map(block => [toDisplayText(block.id), block])), [data.blocks])
  const sourceById = useMemo(() => new Map(data.sources.map(source => [toDisplayText(source.id), source])), [data.sources])

  const tree = useMemo(() => buildCaseNameTree(content, rootTitle), [content, rootTitle])
  const defaultCollapsedScenes = useMemo(() => new Set(
    tree?.children.flatMap(module => module.children.map(scene => scene.id)) ?? [],
  ), [tree])
  const pointSceneIds = useMemo(() => {
    const map = new Map<string, string>()
    tree?.children.forEach(module => module.children.forEach(scene => scene.children.forEach(point => map.set(point.id, scene.id))))
    return map
  }, [tree])

  const gapEntries = useMemo<GapEntry[]>(() => data.gaps.map((gap, index) => {
    const id = toDisplayText(gap.id) || `gap-${index}`
    const objectIds = new Set(refValues(gap, 'testObjectIds'))
    const blockIds = new Set(refValues(gap, 'materialBlockIds'))
    const relatedPointIds = pointEntries.filter(({ point }) => {
      if (objectIds.size) return refValues(point, 'testObjectIds').some(value => objectIds.has(value))
      if (blockIds.size) return refValues(point, 'materialBlockIds').some(value => blockIds.has(value))
      return false
    }).map(entry => entry.id)
    return { id, gap, relatedPointIds }
  }), [data.gaps, pointEntries])

  const activeGap = gapEntries.find(entry => entry.id === activeGapId) ?? gapEntries[0]

  const updateName = useCallback((id: string, name: string) => {
    if (!onChange || !data.artifact) return
    const next = {
      ...data.artifact,
      reviewStatus: 'self_review_only',
      testPoints: data.points.map(point => (toDisplayText(point.id) || '') === id ? { ...point, name } : point),
    }
    onChange(JSON.stringify(next, null, 2))
  }, [data.artifact, data.points, onChange])

  const renderRelations = useCallback((node: CaseNameTreeNode) => {
    if (node.kind === 'point') {
      const entry = entriesById.get(node.id)
      return entry
        ? <PointRelations entry={entry} blockById={blockById} sourceById={sourceById} onRename={onChange ? updateName : undefined} />
        : <div className="ai-tp-relations-empty">未找到该测试点的关联信息</div>
    }
    const entries = collectPointIds(node)
      .map(id => entriesById.get(id))
      .filter((entry): entry is PointEntry => Boolean(entry))
    return <GroupRelations node={node} entries={entries} blockById={blockById} sourceById={sourceById} />
  }, [blockById, entriesById, onChange, sourceById, updateName])

  const locateGap = useCallback((gap: GapEntry) => {
    const sceneIds = [...new Set(gap.relatedPointIds
      .map(id => pointSceneIds.get(id))
      .filter((id): id is string => Boolean(id)))]
    setRevealSceneIds(sceneIds)
    setHighlightedPointIds(gap.relatedPointIds)
    setPage('points')
  }, [pointSceneIds])

  if (data.artifact?.artifactType !== 'traceable_test_points') {
    return <Empty description="测试点格式无效，请重新生成" />
  }

  const review = toDisplayText(data.artifact.reviewStatus)
  const reviewLabel = ({ independent_reviewed: '独立审查通过', independent_review_failed: '独立审查未通过', self_review_only: '仅完成自审' } as Record<string, string>)[review] || '审查状态未知'

  return <div className="ai-traceable-points">
    <div className="ai-tp-page-tabs" role="tablist" aria-label="测试点视图">
      <button
        type="button"
        role="tab"
        aria-selected={page === 'points'}
        className={`ai-tp-page-tab${page === 'points' ? ' is-active' : ''}`}
        onClick={() => setPage('points')}
      >
        测试点<span className="ai-tp-page-count">{pointEntries.length}</span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={page === 'issues'}
        className={`ai-tp-page-tab${page === 'issues' ? ' is-active' : ''}`}
        onClick={() => setPage('issues')}
      >
        审查<span className={`ai-tp-page-count${data.issues.length ? ' is-danger' : ''}`}>{data.issues.length}</span>
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={page === 'gaps'}
        className={`ai-tp-page-tab${page === 'gaps' ? ' is-active' : ''}`}
        onClick={() => setPage('gaps')}
      >
        缺口<span className={`ai-tp-page-count${gapEntries.length ? ' is-warn' : ''}`}>{gapEntries.length}</span>
      </button>
    </div>
    <div className="ai-tp-page-body">
      <div className="ai-tp-page ai-tp-points-page" hidden={page !== 'points'}>
        <CaseNameTreeView
          content={content}
          rootTitle={rootTitle}
          expanded={expanded}
          treeData={tree ?? undefined}
          defaultCollapsed={defaultCollapsedScenes}
          revealNodeIds={revealSceneIds}
          highlightedNodeIds={highlightedPointIds}
          showSaveImage
          fitViewOnMount
          toolbarHint="点击场景展开测试点；悬停节点显示关联按钮"
          renderRelations={renderRelations}
        />
      </div>
      <div className="ai-tp-page ai-tp-issues-page" hidden={page !== 'issues'}>
        <TraceableIssuesReview issues={data.issues} reviewStatus={review} reviewLabel={reviewLabel} />
      </div>
      <div className="ai-tp-page ai-tp-review-page" hidden={page !== 'gaps'}>
        <TraceableGapsReview
          gaps={gapEntries}
          activeGap={activeGap}
          pointById={entriesById}
          blockById={blockById}
          sourceById={sourceById}
          onSelectGap={setActiveGapId}
          onLocate={locateGap}
        />
      </div>
    </div>
  </div>
}
