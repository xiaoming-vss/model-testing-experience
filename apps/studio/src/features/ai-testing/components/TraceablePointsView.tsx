import { useCallback, useMemo, useState } from 'react'
import { Empty, Input, Tag } from 'antd'
import { CaseNameTreeView } from './CaseNamesResultView'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import {
  ArtifactDetailTitle,
  ArtifactDivider,
  ArtifactEmpty,
  ArtifactEvidence,
  ArtifactEvidenceItem,
  ArtifactEvidenceMissing,
  ArtifactHeader,
  ArtifactKicker,
  ArtifactListRow,
  ArtifactRefChips,
  ArtifactSectionHead,
  ArtifactSplit,
  ArtifactStat,
  ArtifactTabs,
} from '@/shared/components/ArtifactView'
import { cx } from '@/shared/utils/cx'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { buildCaseNameTree, type CaseNameTreeNode } from '../utils/caseNameTree'

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

function EvidenceItems({ blockIds, blockById, sourceById, showMissing = false }: {
  blockIds: string[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
  showMissing?: boolean
}) {
  return <>{blockIds.map((id) => {
    const block = blockById.get(id)
    if (!block) return showMissing ? <ArtifactEvidenceMissing key={id}>{id}：未找到对应材料</ArtifactEvidenceMissing> : null
    const source = sourceById.get(toDisplayText(block.sourceId))
    return <ArtifactEvidenceItem key={id} source={toDisplayText(source?.name) || '来源未找到'} locator={toDisplayText(block.locator)}>
      <MaterialBlockContent block={block as MaterialBlock} />
    </ArtifactEvidenceItem>
  })}</>
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

  return <div className="max-h-[min(70vh,560px)] w-[360px] max-w-[min(420px,calc(100vw-40px))] overflow-auto text-app-surface-text">
    <header className="border-b border-app-surface-border px-[14px] pb-2.5 pt-3">
      <ArtifactKicker badge="测试点"><span>{context || '未分组'}</span></ArtifactKicker>
      <strong className="mt-[7px] block text-[13px] leading-[1.45] text-app-surface-text [overflow-wrap:anywhere]">{id} {name}</strong>
    </header>
    {onRename ? <label className="flex flex-col gap-1 px-[14px] pt-2.5">
      <span className="text-[10.5px] text-app-surface-text-muted">名称</span>
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
      <em className="text-[10px] not-italic text-app-surface-text-muted">修改后审查状态会重置为自审</em>
    </label> : null}
    {hasRefs ? <div className="flex flex-col gap-3 px-[14px] pt-2.5">
      {groups.map(group => group.values.length > 0
        ? group.field === 'materialBlockIds'
          ? <ArtifactEvidence key={group.field} title={group.label} count={group.values.length} className="mt-0">
            <EvidenceItems blockIds={group.values} blockById={blockById} sourceById={sourceById} />
          </ArtifactEvidence>
          : <ArtifactRefChips key={group.field} title={group.label} values={group.values} className="mt-0" />
        : null)}
    </div> : <div className="px-[14px] py-2.5 text-[10.5px] text-app-surface-text-muted">暂无关联依据</div>}
    <footer className="mt-2.5 border-t border-app-surface-border px-[14px] pb-2.5 pt-2 text-[10px] leading-[1.5] text-app-surface-text-muted">引用来自冻结的材料与测试范围分析。</footer>
  </div>
}

function GroupRelations({ node, entries, blockById, sourceById }: {
  node: CaseNameTreeNode
  entries: PointEntry[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  const refs = aggregateRefs(entries)
  return <div className="max-h-[min(70vh,560px)] w-[360px] max-w-[min(420px,calc(100vw-40px))] overflow-auto text-app-surface-text">
    <header className="border-b border-app-surface-border px-[14px] pb-2.5 pt-3">
      <ArtifactKicker badge={node.kind === 'root' ? '全部测试点' : '分组'} badgeTone="muted" />
      <strong className="mt-[7px] block text-[13px] leading-[1.45] text-app-surface-text [overflow-wrap:anywhere]">{node.title}</strong>
      <small className="mt-[5px] block text-[10.5px] leading-[1.5] text-app-surface-text-muted">{entries.length} 个测试点 · {refs.materialBlockIds.length} 个材料块 · {refs.riskIds.length} 个风险</small>
    </header>
    <div className="flex flex-col gap-3 px-[14px] pt-2.5">
      <section>
        <ArtifactSectionHead title="包含的测试点" count={entries.length} />
        {entries.length ? <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {entries.map(({ id, point }) => <li key={id} className="flex items-center gap-[7px] rounded-[5px] border border-transparent px-[7px] py-[5px] text-[10.5px]">
            <span className="flex-none font-mono text-[9.5px] text-app-accent">{id}</span>
            <span className="min-w-0 flex-1 truncate">{toDisplayText(point.name) || id}</span>
            <em className="flex-none text-[9.5px] not-italic text-app-surface-text-muted">{totalRefCount(point)} 项</em>
          </li>)}
        </ul> : <div className="py-2.5 text-[10.5px] text-app-surface-text-muted">暂无测试点</div>}
      </section>
      {refs.materialBlockIds.length ? <ArtifactEvidence title="聚合材料块" count={refs.materialBlockIds.length} className="mt-0">
        <EvidenceItems blockIds={refs.materialBlockIds} blockById={blockById} sourceById={sourceById} />
      </ArtifactEvidence> : null}
      {refs.riskIds.length ? <ArtifactRefChips title="涉及风险" values={refs.riskIds} className="mt-0" /> : null}
    </div>
    <footer className="mt-2.5 border-t border-app-surface-border px-[14px] pb-2.5 pt-2 text-[10px] leading-[1.5] text-app-surface-text-muted">分组关联会聚合其下全部测试点的依据。</footer>
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
  if (!groups.length) return <p className="mt-3 text-[11px] text-app-surface-text-muted">暂无关联依据</p>
  return <div className="mt-3.5 flex flex-col gap-3 [&>*+*]:border-t [&>*+*]:border-app-surface-border [&>*+*]:pt-3">
    {groups.map(group => group.field === 'materialBlockIds'
      ? <ArtifactEvidence key={group.field} title={group.label} count={group.values.length} className="mt-0">
        <EvidenceItems blockIds={group.values} blockById={blockById} sourceById={sourceById} showMissing />
      </ArtifactEvidence>
      : <ArtifactRefChips key={group.field} title={group.label} values={group.values} className="mt-0" />)}
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
  const emptyText = reviewStatus === 'independent_reviewed'
    ? '独立审查通过，没有未解决的审查问题'
    : '没有未解决的审查问题'

  return <div className="flex h-full min-h-0 flex-col gap-2.5">
    <ArtifactHeader>
      <ArtifactStat
        label="未解决审查问题"
        value={issues.length}
        tone={issues.length ? 'danger' : 'ok'}
        trailing={<Tag color={issues.length ? 'orange' : reviewStatus === 'independent_reviewed' ? 'green' : 'orange'}>{reviewLabel}</Tag>}
      />
    </ArtifactHeader>
    {issues.length ? <ArtifactSplit
      listLabel="未解决的审查问题列表"
      detailLabel="审查问题详情"
      listMaxHeight="190"
      list={issues.map((issue, index) => <ArtifactListRow
        key={index}
        id={toDisplayText(issue.targetId) || '遗漏项'}
        title={toDisplayText(issue.issue) || '未记录问题描述'}
        active={index === safeIndex}
        activeTone="danger"
        idTone="danger"
        onClick={() => setActiveIndex(index)}
      />)}
      detail={<>
        <ArtifactKicker badge="审查问题" badgeTone="danger"><span>{targetId}</span></ArtifactKicker>
        <ArtifactDetailTitle>{issueText}</ArtifactDetailTitle>
        {suggestion
          ? <div className="mt-3 flex items-start gap-[9px] rounded-[7px] border border-app-surface-border border-l-2 border-l-app-accent bg-app-surface-hover px-[10px] py-[9px]">
            <strong className="flex-none text-[10px] [font-weight:650] text-app-accent">建议</strong>
            <span className="text-[11.5px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{suggestion}</span>
          </div>
          : <p className="mt-3 text-[11px] text-app-surface-text-muted">暂无修改建议</p>}
      </>}
    /> : <ArtifactEmpty description={emptyText} />}
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

  return <div className="flex h-full min-h-0 flex-col gap-2.5">
    <ArtifactHeader>
      <ArtifactStat label="覆盖缺口" value={gaps.length} tone={gaps.length ? 'warn' : 'ok'} />
      <ArtifactDivider />
      <ArtifactStat label="关联测试点" value={relatedPointCount} />
    </ArtifactHeader>
    {gaps.length ? <ArtifactSplit
      listLabel="覆盖缺口列表"
      detailLabel="覆盖缺口详情"
      listMaxHeight="190"
      list={gaps.map(gap => <ArtifactListRow
        key={gap.id}
        id={gap.id}
        title={toDisplayText(gap.gap.description) || '未命名覆盖缺口'}
        active={gap.id === activeGap?.id}
        activeTone="warn"
        idTone="warn"
        onClick={() => onSelectGap(gap.id)}
      />)}
      detail={activeGap ? <>
        <ArtifactKicker badge="覆盖缺口" badgeTone="warn"><span>{activeGap.id}</span></ArtifactKicker>
        <ArtifactDetailTitle>{activeDescription}</ArtifactDetailTitle>
        <div className="mt-3 flex items-start gap-[9px] rounded-[7px] border border-app-status-warning-border bg-app-status-warning-bg px-[10px] py-[9px]">
          <strong className="flex-none text-[10px] [font-weight:650] text-app-status-warning-text">暂缓覆盖</strong>
          <span className="text-[11.5px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{blockedCoverage}</span>
        </div>
        <GapReferenceGroups gap={activeGap.gap} blockById={blockById} sourceById={sourceById} />
        {relatedPoints.length ? <section className="mt-[18px] border-t border-app-surface-border pt-[14px]">
          <ArtifactSectionHead
            title="关联测试点"
            count={relatedPoints.length}
            action={<button type="button" className="rounded-[5px] border border-app-accent-border bg-app-accent-surface px-2 py-1 text-[10px] text-app-accent hover:border-app-accent" onClick={() => onLocate(activeGap)}>在树图中查看</button>}
          />
          <div className="mt-2 flex flex-wrap gap-[5px]">
            {relatedPoints.map(entry => <span key={entry.id} className="rounded-[5px] border border-app-surface-border bg-app-surface-hover px-1.5 py-[3px] text-[10.5px] leading-[1.4] text-app-surface-text [overflow-wrap:anywhere]">{entry.id} {toDisplayText(entry.point.name) || entry.id}</span>)}
          </div>
        </section> : null}
      </> : null}
    /> : <ArtifactEmpty description="未记录覆盖缺口" />}
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
        : <div className="px-[14px] py-2.5 text-[10.5px] text-app-surface-text-muted">未找到该测试点的关联信息</div>
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

  return <div className="flex min-h-0 flex-1 flex-col bg-app-surface">
    <ArtifactTabs
      ariaLabel="测试点视图"
      active={page}
      onChange={setPage}
      tabs={[
        { key: 'points', label: '测试点', count: pointEntries.length },
        { key: 'issues', label: '审查', count: data.issues.length, tone: data.issues.length ? 'danger' : undefined },
        { key: 'gaps', label: '缺口', count: gapEntries.length, tone: gapEntries.length ? 'warn' : undefined },
      ]}
    />
    <div className="flex min-h-0 flex-1 flex-col">
      <div hidden={page !== 'points'} className={cx('h-full min-h-0 flex-col gap-2.5 px-3 pb-3 pt-2.5 [&_.ai-case-name-tree]:min-h-0 [&_.ai-case-name-tree]:flex-1 [&_.ai-case-tree-shell]:min-h-0 [&_.ai-case-tree-shell]:flex-1 max-narrow:min-h-[440px]', page === 'points' && 'flex')}>
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
      <div hidden={page !== 'issues'} className={cx('h-full min-h-0 flex-col gap-2.5 px-3 pb-3 pt-2.5 max-narrow:overflow-auto', page === 'issues' && 'flex')}>
        <TraceableIssuesReview issues={data.issues} reviewStatus={review} reviewLabel={reviewLabel} />
      </div>
      <div hidden={page !== 'gaps'} className={cx('h-full min-h-0 flex-col gap-2.5 px-3 pb-3 pt-2.5 max-narrow:overflow-auto', page === 'gaps' && 'flex')}>
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
