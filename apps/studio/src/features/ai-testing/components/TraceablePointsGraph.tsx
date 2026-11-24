import { Background, BackgroundVariant, Handle, Position, ReactFlow, type NodeProps, type ReactFlowInstance } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CheckCircleFilled, EditOutlined, FileTextOutlined, WarningOutlined } from '@ant-design/icons'
import { createContext, forwardRef, useContext, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { saveFlowImage } from '@/shared/utils/flowImage'
import { cx } from '@/shared/utils/cx'
import { toDisplayText } from '../utils/functionalOutput'
import {
  buildTraceablePointsGraph,
  type TraceableFlowEdge,
  type TraceableFlowNode,
  type TraceableMode,
  type TraceableNodeData,
  type TraceableSelection,
} from '../utils/traceablePointsGraph'
import type { TraceableGap, TraceableIssue, TraceablePoint, TraceablePointsModel, TraceableRefs } from '../utils/traceablePointsModel'
import styles from '../styles/traceable-points.module.css'

export type TraceableEvidenceRequest = {
  title: string
  blockIds: string[]
  refs?: TraceableRefs
}

type GraphActions = {
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
  pointById: Map<string, TraceablePoint>
  canRenamePoints: boolean
  onSelect: (selection: TraceableSelection) => void
  onSceneSelect: (sceneId: string) => void
  onFindPoint: (pointId: string) => void
  onRenamePoint: (pointId: string, name: string) => void
  onOpenEvidence: (request: TraceableEvidenceRequest) => void
}

const GraphActionsContext = createContext<GraphActions | null>(null)

function useGraphActions() {
  const actions = useContext(GraphActionsContext)
  if (!actions) throw new Error('测试点图谱缺少操作上下文')
  return actions
}

function sourceNames(point: TraceablePoint, blockById: Map<string, Record<string, unknown>>, sourceById: Map<string, Record<string, unknown>>) {
  return [...new Set(point.refs.materialBlockIds.map((id) => {
    const block = blockById.get(id)
    const source = block ? sourceById.get(toDisplayText(block.sourceId)) : undefined
    return toDisplayText(source?.name)
  }).filter(Boolean))]
}

const RELATION_GROUPS = [
  { key: 'testObjectIds', label: '对象', tone: 'accent' },
  { key: 'impactAreaIds', label: '范围', tone: 'neutral' },
  { key: 'riskIds', label: '风险', tone: 'warn' },
  { key: 'scopeQuestionIds', label: '待确认', tone: 'neutral' },
  { key: 'materialQuestionIds', label: '材料问题', tone: 'neutral' },
] as const

const CHIP_TONE: Record<'accent' | 'neutral' | 'warn', string> = {
  accent: 'border-app-accent-border bg-app-accent-surface text-app-accent',
  neutral: 'border-app-surface-border bg-app-surface-hover text-app-surface-text',
  warn: 'border-app-status-warning-border bg-app-status-warning-bg text-app-status-warning-text',
}

export function TraceablePointDetailCard({ point, blockById, sourceById, canRename, onOpenEvidence, onRename }: {
  point: TraceablePoint
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
  canRename: boolean
  onOpenEvidence: (request: TraceableEvidenceRequest) => void
  onRename: (pointId: string, name: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(point.name)
  useEffect(() => {
    setEditing(false)
    setDraft(point.name)
  }, [point.id, point.name])
  const names = sourceNames(point, blockById, sourceById)
  const groups = RELATION_GROUPS
    .map(group => ({ ...group, values: point.refs[group.key] }))
    .filter(group => group.values.length > 0)

  const save = () => {
    const next = draft.trim()
    if (next && next !== point.name) onRename(point.id, next)
    setEditing(false)
  }

  return <article className={styles.pointDetail} aria-label="测试点详情">
    <div className="flex items-center gap-1.5">
      {point.derived ? <span className="inline-flex h-[20px] items-center rounded-[4px] border border-app-status-warning-border bg-app-status-warning-bg px-1.5 text-[10.5px] leading-none text-app-status-warning-text" title="由材料规则推导">推断</span> : null}
      {canRename ? <button type="button" className="nodrag ml-auto inline-flex size-6 cursor-pointer items-center justify-center rounded-[5px] border border-transparent bg-transparent text-app-surface-text-muted transition-colors hover:border-app-surface-border hover:bg-app-surface-hover hover:text-app-surface-text" title="编辑名称" aria-label="编辑测试点名称" onClick={() => { setDraft(point.name); setEditing(true) }}><EditOutlined aria-hidden /></button> : null}
    </div>
    {editing
      ? <div className="mt-2 flex flex-col gap-1.5">
        <input
          className="nodrag h-8 w-full rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[12px] text-app-surface-text outline-none focus:border-app-accent-border focus:ring-2 focus:ring-app-accent-selection"
          value={draft}
          aria-label="测试点名称"
          onChange={event => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') save()
            if (event.key === 'Escape') { setEditing(false); setDraft(point.name) }
          }}
          autoFocus
        />
        <div className="flex items-center gap-1.5">
          <button type="button" className="inline-flex h-6 cursor-pointer items-center rounded-[5px] border border-app-accent-border bg-app-accent-surface px-2 text-[10.5px] text-app-accent" onClick={save}>保存名称</button>
          <button type="button" className="inline-flex h-6 cursor-pointer items-center rounded-[5px] border border-app-surface-border bg-app-surface px-2 text-[10.5px] text-app-surface-text-muted hover:text-app-surface-text" onClick={() => { setEditing(false); setDraft(point.name) }}>取消</button>
          <span className="text-[10px] text-app-surface-text-muted">修改后审查状态会重置为自审</span>
        </div>
      </div>
      : <h3 className="m-0 mt-2 text-[13px] leading-[1.45] font-semibold text-app-surface-text [overflow-wrap:anywhere]">{point.name}</h3>}
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-app-surface-text-muted">
      <span>材料 <b className="font-semibold text-app-surface-text">{point.refs.materialBlockIds.length}</b></span>
      <span>对象 <b className="font-semibold text-app-surface-text">{point.refs.testObjectIds.length}</b></span>
      <span>影响 <b className="font-semibold text-app-surface-text">{point.refs.impactAreaIds.length}</b></span>
      <span>风险 <b className="font-semibold text-app-surface-text">{point.refs.riskIds.length}</b></span>
    </div>
    <div className={styles.cardSection}>
      <span className="mb-1.5 block text-[10.5px] text-app-surface-text-muted">关联依据</span>
      {groups.length
        ? <div className="flex flex-wrap gap-1">
          {groups.flatMap(group => group.values.map(value => <span key={`${group.key}:${value}`} title={value} className={cx('inline-flex h-[21px] max-w-full items-center rounded-[4px] border px-1.5 text-[10.5px]', CHIP_TONE[group.tone])}>{group.label} {value}</span>))}
        </div>
        : <span className="text-[10.5px] text-app-surface-text-muted">暂无关联依据</span>}
    </div>
    <div className={styles.cardSection}>
      <span className="mb-1.5 block text-[10.5px] text-app-surface-text-muted">材料依据</span>
      <div className="flex min-w-0 items-center gap-1.5 text-[10.5px] text-app-surface-text">
        <FileTextOutlined className="shrink-0 text-app-surface-text-muted" aria-hidden />
        <span className="min-w-0 flex-1 truncate" title={names.join('、')}>{names.length ? names.join('、') : '材料内容未提供'}</span>
        {point.refs.materialBlockIds.length ? <button type="button" className="nodrag inline-flex h-6 shrink-0 cursor-pointer items-center rounded-[5px] border border-app-accent-border bg-app-accent-surface px-2 text-[10.5px] text-app-accent" onClick={() => onOpenEvidence({ title: point.name, blockIds: point.refs.materialBlockIds, refs: point.refs })}>查看 {point.refs.materialBlockIds.length} 块</button> : null}
      </div>
    </div>
    {point.derived ? <p className="m-0 mt-2 text-[10.5px] leading-[1.5] text-app-surface-text-muted">由材料依据推导，生成用例前建议人工确认前提。</p> : null}
  </article>
}

function TraceableGapCard({ gap, pointById, onFindPoint, onOpenEvidence }: {
  gap: TraceableGap
  pointById: Map<string, TraceablePoint>
  onFindPoint: (pointId: string) => void
  onOpenEvidence: (request: TraceableEvidenceRequest) => void
}) {
  return <article className={styles.gapCard} aria-label="覆盖缺口详情">
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="font-mono text-[10px] text-app-status-warning-text">{gap.id}</span>
      <span className="inline-flex h-[20px] items-center rounded-[4px] border border-app-status-warning-border bg-app-surface px-1.5 text-[10.5px] leading-none text-app-status-warning-text">暂缓覆盖</span>
      <span className="ml-auto text-[10px] text-app-surface-text-muted">{gap.relatedPointIds.length} 个测试点</span>
    </div>
    <h3 className="m-0 mt-2 text-[13px] leading-[1.45] font-semibold text-app-surface-text [overflow-wrap:anywhere]">{gap.description}</h3>
    <div className="mt-2 flex items-start gap-1.5 rounded-[6px] border border-app-status-warning-border bg-app-surface px-2 py-1.5">
      <WarningOutlined className="mt-px shrink-0 text-app-status-warning-text" aria-hidden />
      <div className="min-w-0 text-[10.5px] leading-[1.55] text-app-surface-text"><strong className="mr-1 text-app-status-warning-text">暂缓覆盖</strong>{gap.blockedCoverage}</div>
    </div>
    <div className={styles.cardSection}>
      <span className="mb-1.5 block text-[10.5px] text-app-surface-text-muted">关联测试点</span>
      {gap.relatedPointIds.length
        ? <div className="flex flex-wrap gap-1">
          {gap.relatedPointIds.map((pointId) => {
            const point = pointById.get(pointId)
            return <button key={pointId} type="button" className="nodrag inline-flex max-w-full cursor-pointer items-center rounded-[4px] border border-app-surface-border bg-app-surface px-1.5 py-1 text-left text-[10.5px] leading-[1.4] text-app-surface-text hover:border-app-accent-border hover:bg-app-surface-hover" title={point?.name} onClick={() => onFindPoint(pointId)}>{point?.name ?? '关联测试点'}</button>
          })}
        </div>
        : <span className="text-[10.5px] text-app-surface-text-muted">暂无关联测试点</span>}
    </div>
    <div className={styles.cardSection}>
      <span className="mb-1.5 block text-[10.5px] text-app-surface-text-muted">材料依据</span>
      {gap.refs.materialBlockIds.length
        ? <button type="button" className="nodrag inline-flex h-6 cursor-pointer items-center gap-1 rounded-[5px] border border-app-accent-border bg-app-accent-surface px-2 text-[10.5px] text-app-accent" onClick={() => onOpenEvidence({ title: gap.id, blockIds: gap.refs.materialBlockIds, refs: gap.refs })}><FileTextOutlined aria-hidden />查看 {gap.refs.materialBlockIds.length} 块</button>
        : <span className="text-[10.5px] text-app-surface-text-muted">暂无材料依据</span>}
    </div>
  </article>
}

const ISSUE_KIND_LABEL: Record<string, string> = {
  unsupported: '依据不足',
  missing: '遗漏',
  granularity: '粒度过粗',
  classification: '分类问题',
}

function targetKindLabel(kind: 'point' | 'gap' | 'missing') {
  return kind === 'point' ? '测试点' : kind === 'gap' ? '覆盖缺口' : '遗漏项'
}

function TraceableIssueCard({ issue, targetLabel, targetKind, onFindPoint }: {
  issue: TraceableIssue
  targetLabel: string
  targetKind: 'point' | 'gap' | 'missing'
  onFindPoint: (pointId: string) => void
}) {
  return <article className={styles.issueCard} aria-label="审查问题详情">
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex h-[20px] items-center rounded-[4px] border border-app-request-error-border bg-app-danger-surface-soft px-1.5 text-[10.5px] leading-none text-app-request-error-text">{ISSUE_KIND_LABEL[issue.kind] ?? '审查问题'}</span>
      <span className="text-[10.5px] text-app-surface-text-muted">{targetKindLabel(targetKind)} · {targetLabel}</span>
    </div>
    <h3 className="m-0 mt-2 text-[13px] leading-[1.5] font-semibold text-app-surface-text [overflow-wrap:anywhere]">{issue.issue}</h3>
    {issue.suggestion
      ? <div className="mt-2 flex items-start gap-1.5 rounded-[6px] border border-app-surface-border border-l-2 border-l-app-accent bg-app-surface-hover px-2 py-1.5">
        <strong className="shrink-0 text-[10px] text-app-accent">建议</strong>
        <span className="text-[10.5px] leading-[1.55] text-app-surface-text [overflow-wrap:anywhere]">{issue.suggestion}</span>
      </div>
      : <p className="m-0 mt-2 text-[10.5px] text-app-surface-text-muted">暂无修改建议</p>}
    {targetKind === 'point' && issue.pointId
      ? <button type="button" className="nodrag mt-2 inline-flex h-6 cursor-pointer items-center rounded-[5px] border border-app-accent-border bg-app-accent-surface px-2 text-[10.5px] text-app-accent" onClick={() => onFindPoint(issue.pointId!)}>查看关联测试点</button>
      : null}
  </article>
}

function TraceableReviewCard({ data }: { data: Extract<TraceableNodeData, { kind: 'review' }> }) {
  const reviewed = data.reviewStatus === 'independent_reviewed'
  const failed = data.reviewStatus === 'independent_review_failed'
  const title = reviewed
    ? '独立审查通过，没有未解决的审查问题'
    : failed
      ? '审查未通过，但没有记录具体问题'
      : '没有未解决的审查问题'
  const copy = reviewed
    ? '当前测试点产物已完成独立审查，未记录阻断、重要或次要审查问题。审查结果仅供人工判断，不会自动修改测试点。'
    : failed
      ? '审查状态为未通过，但产物没有携带具体审查意见，请回到上游确认。'
      : '独立审查尚未进行。审查结果仅供人工判断，不会自动修改测试点。'
  return <article className={styles.reviewCard} aria-label="审查结果">
    <span className={cx(reviewed ? 'text-app-status-approved-text' : 'text-app-status-warning-text')}><CheckCircleFilled className="text-[22px]" aria-hidden /></span>
    <h3 className="m-0 mt-3 text-[14px] leading-[1.45] font-semibold text-app-surface-text">{title}</h3>
    <p className="m-0 mt-2 text-[11px] leading-[1.6] text-app-surface-text-muted">{copy}</p>
    <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-[10.5px] text-app-surface-text-muted">
      <span><b className="text-[13px] text-app-surface-text">{data.pointCount}</b> 测试点</span>
      <span><b className="text-[13px] text-app-surface-text">{data.gapCount}</b> 覆盖缺口</span>
      <span><b className="text-[13px] text-app-surface-text">{data.moduleCount}</b> 模块</span>
    </div>
    <div className="mt-3 flex items-center gap-1.5 border-t border-app-surface-border pt-2 text-[10.5px] text-app-surface-text-muted">
      <i className={cx('size-1.5 rounded-full', reviewed ? 'bg-app-status-approved-text' : 'bg-app-status-warning-text')} aria-hidden />
      {data.reviewLabel}
    </div>
  </article>
}

function TreeGraphNode({ data }: { data: Extract<TraceableNodeData, { kind: 'root' | 'module' | 'scene' }> }) {
  const actions = useGraphActions()
  const isPointBearing = data.kind === 'scene'
  const selected = data.selected
  const highlighted = data.kind === 'scene' && data.highlighted
  const className = data.kind === 'root'
    ? 'ai-case-name-tree-root'
    : `ai-case-name-tree-node ${data.kind === 'module' ? 'model' : 'test-model'}`
  const title = data.kind === 'root'
    ? `${data.title} · ${data.pointCount} 个测试点`
    : data.kind === 'module'
      ? `${data.title} · ${data.pointCount} 个测试点 · ${data.sceneCount} 个场景`
      : `${data.title} · ${data.pointCount} 个测试点 · ${data.expanded ? '点击收起测试点' : '点击展开测试点'}`
  const activate = () => {
    if (data.kind === 'root') actions.onSelect({ kind: 'overview' })
    else if (data.kind === 'module') actions.onSelect({ kind: 'module', id: data.id })
    else actions.onSceneSelect(data.id)
  }
  return <>
    {data.kind !== 'root' ? <Handle type="target" position={Position.Left} className={styles.handle} /> : null}
    <div className={cx(styles.treeNodeWrap, selected && styles.treeNodeWrapSelected, highlighted && styles.treeNodeWrapRelated)}>
      <div
        className={cx(className, highlighted && 'is-related', 'cursor-pointer')}
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        aria-expanded={isPointBearing ? data.expanded : undefined}
        aria-label={data.kind === 'root' ? `全部测试点，${data.pointCount} 个` : data.kind === 'module' ? `模块：${data.title}` : `场景：${data.title}，${data.pointCount} 个测试点`}
        title={title}
        onClick={(event) => { event.stopPropagation(); activate() }}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); activate() } }}
      >
        <span className={cx('ai-case-name-tree-node-label', styles.treeLabel)}>{data.title}</span>
      </div>
    </div>
    <Handle type="source" position={Position.Right} className={styles.handle} />
  </>
}

function PointGraphNode({ point, selected, highlighted }: { point: TraceablePoint; selected: boolean; highlighted: boolean }) {
  const actions = useGraphActions()
  return <>
    <Handle type="target" position={Position.Left} className={styles.handle} />
    <div className={styles.pointWrap}>
      <div
        className={cx('ai-case-name-tree-node point', styles.pointNode, highlighted && 'is-related', selected && 'is-selected')}
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        aria-label={`测试点：${point.name}`}
        title={point.name}
        onClick={(event) => { event.stopPropagation(); actions.onSelect({ kind: 'point', id: point.id }) }}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); actions.onSelect({ kind: 'point', id: point.id }) } }}
      >
        <span className={cx('ai-case-name-tree-node-label', styles.pointName, point.derived && styles.pointNameInferred)}>{point.name}</span>
      </div>
      {point.derived ? <span className={styles.inferredFlag} title="由材料规则推导">推断</span> : null}
    </div>
    <Handle type="source" position={Position.Right} className={styles.handle} />
  </>
}

function TraceableNode({ data }: NodeProps<TraceableFlowNode>) {
  const actions = useGraphActions()
  if (data.kind === 'root' || data.kind === 'module' || data.kind === 'scene') return <TreeGraphNode data={data} />
  if (data.kind === 'point') return <PointGraphNode point={data.point} selected={data.selected} highlighted={data.highlighted} />
  if (data.kind === 'detail') {
    return <>
      <Handle type="target" position={Position.Left} className={styles.handle} />
      <TraceablePointDetailCard
        point={data.point}
        blockById={actions.blockById}
        sourceById={actions.sourceById}
        canRename={actions.canRenamePoints && Boolean(data.point.rawId)}
        onOpenEvidence={actions.onOpenEvidence}
        onRename={actions.onRenamePoint}
      />
    </>
  }
  if (data.kind === 'gap') {
    return <>
      <Handle type="target" position={Position.Left} className={styles.handle} />
      <TraceableGapCard gap={data.gap} pointById={actions.pointById} onFindPoint={actions.onFindPoint} onOpenEvidence={actions.onOpenEvidence} />
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </>
  }
  if (data.kind === 'review') return <><Handle type="target" position={Position.Left} className={styles.handle} /><TraceableReviewCard data={data} /></>
  return <><Handle type="target" position={Position.Left} className={styles.handle} /><TraceableIssueCard issue={data.issue} targetLabel={data.targetLabel} targetKind={data.targetKind} onFindPoint={actions.onFindPoint} /></>
}

const nodeTypes = { traceable: TraceableNode }

export type TraceablePointsGraphHandle = {
  saveImage: () => Promise<void>
  fitView: () => void
}

type TraceablePointsGraphProps = {
  model: TraceablePointsModel
  mode: TraceableMode
  selection: TraceableSelection
  expandedSceneIds: ReadonlySet<string>
  activeGap?: TraceableGap
  activeIssue?: TraceableIssue
  rootTitle: string
  canRenamePoints?: boolean
  onSelect: (selection: TraceableSelection) => void
  onSceneSelect: (sceneId: string) => void
  onFindPoint: (pointId: string) => void
  onRenamePoint: (pointId: string, name: string) => void
  onOpenEvidence: (request: TraceableEvidenceRequest) => void
}

export const TraceablePointsGraph = forwardRef<TraceablePointsGraphHandle, TraceablePointsGraphProps>(function TraceablePointsGraph({ model, mode, selection, expandedSceneIds, activeGap, activeIssue, rootTitle, canRenamePoints = false, onSelect, onSceneSelect, onFindPoint, onRenamePoint, onOpenEvidence }, ref) {
  const graph = useMemo(() => buildTraceablePointsGraph({
    modules: model.modules,
    rootTitle,
    mode,
    expandedSceneIds,
    selection,
    activeGap,
    activeIssue,
    issueCount: model.issues.length,
    totalPoints: model.points.length,
    totalGaps: model.gaps.length,
    reviewStatus: model.reviewStatus,
    reviewLabel: model.reviewLabel,
  }), [activeGap, activeIssue, expandedSceneIds, model, mode, rootTitle, selection])
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<TraceableFlowNode, TraceableFlowEdge> | null>(null)
  const [canvasSize, setCanvasSize] = useState<{ width: number; height: number } | null>(null)
  const [fitRequest, setFitRequest] = useState<{ mode: TraceableMode; tick: number } | null>(null)

  useLayoutEffect(() => {
    const element = canvasRef.current
    if (!element) return
    const measure = () => {
      const width = element.clientWidth || Math.round(element.getBoundingClientRect().width) || 1200
      const height = element.clientHeight || Math.round(element.getBoundingClientRect().height) || 800
      setCanvasSize(current => current?.width === width && current.height === height ? current : { width, height })
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const defaultViewport = useMemo(() => {
    if (!canvasSize) return undefined
    const fitMode = fitRequest?.mode === mode
    const zoom = fitMode
      ? Math.min(1.05, Math.max(0.3, Math.min(
        (canvasSize.width - 32) / Math.max(graph.stageWidth, 1),
        (canvasSize.height - 32) / Math.max(graph.stageHeight, 1),
      )))
      : Math.min(1.05, Math.max(0.3, (canvasSize.width - 48) / Math.max(graph.stageWidth, 1)))
    return {
      x: Math.max(16, (canvasSize.width - graph.stageWidth * zoom) / 2),
      y: Math.max(16, fitMode ? (canvasSize.height - graph.stageHeight * zoom) / 2 : (canvasSize.height - graph.stageHeight * zoom) / 2),
      zoom,
    }
  }, [canvasSize, fitRequest?.mode, graph.stageHeight, graph.stageWidth, mode])

  const actions = useMemo<GraphActions>(() => ({
    blockById: model.blockById,
    sourceById: model.sourceById,
    pointById: model.pointById,
    canRenamePoints,
    onSelect,
    onSceneSelect,
    onFindPoint,
    onRenamePoint,
    onOpenEvidence,
  }), [canRenamePoints, model.blockById, model.pointById, model.sourceById, onFindPoint, onOpenEvidence, onRenamePoint, onSceneSelect, onSelect])

  useImperativeHandle(ref, () => ({
    saveImage: async () => {
      const canvas = canvasRef.current
      const flow = flowRef.current
      if (!canvas || !flow) throw new Error('图谱尚未准备完成')
      await saveFlowImage(canvas, flow.getNodes(), `${rootTitle || '测试点'}-测试点图谱.png`)
    },
    fitView: () => {
      setFitRequest({ mode, tick: Date.now() })
    },
  }), [mode, rootTitle])

  return <GraphActionsContext.Provider value={actions}>
    <div ref={canvasRef} className={styles.canvas}>
      {defaultViewport ? <ReactFlow<TraceableFlowNode, TraceableFlowEdge>
        key={`${mode}-${fitRequest?.tick ?? 0}`}
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        defaultViewport={defaultViewport}
        onInit={(instance) => { flowRef.current = instance }}
        onPaneClick={() => onSelect({ kind: 'overview' })}
        nodesDraggable={false}
        onlyRenderVisibleElements={false}
        nodesConnectable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        minZoom={0.3}
        maxZoom={1.6}
        panOnScroll
        zoomOnScroll={false}
        zoomActivationKeyCode="Control"
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--app-graph-edge-muted)" />
      </ReactFlow> : null}
    </div>
  </GraphActionsContext.Provider>
})
