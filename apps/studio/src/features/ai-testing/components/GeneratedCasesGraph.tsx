import { Background, BackgroundVariant, Handle, Position, ReactFlow, type NodeProps, type ReactFlowInstance } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CheckCircleFilled, CloseOutlined, DeleteOutlined, FileTextOutlined, PlayCircleOutlined, SnippetsOutlined } from '@ant-design/icons'
import { Button, Input } from 'antd'
import { createContext, forwardRef, useContext, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { saveFlowImage } from '@/shared/utils/flowImage'
import { cx } from '@/shared/utils/cx'
import { getGeneratedCaseEditableFields, type GeneratedTestCase } from '../utils/functionalOutput'
import {
  buildGeneratedCasesGraph,
  generatedCaseNodeId,
  GENERATED_CASES_STAGE_WIDTH,
  type GeneratedCasesFlowEdge,
  type GeneratedCasesFlowNode,
  type GeneratedCasesNodeData,
  type GeneratedCasesSelection,
} from '../utils/generatedCasesGraph'
import type { GeneratedCaseEntry, GeneratedCasesModel } from '../utils/generatedCasesModel'
import styles from '../styles/generated-cases.module.css'
import workbenchStyles from '../styles/traceable-points.module.css'

const CASE_ID_FIELDS = ['case_id', 'caseId']

function getTagKind(key: string): 'id' | 'type' | 'priority' | 'default' {
  if (CASE_ID_FIELDS.includes(key)) return 'id'
  if (['case_type', 'caseType', 'type'].includes(key)) return 'type'
  if (key === 'priority') return 'priority'
  return 'default'
}

function fieldLines(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.map(item => String(item)).filter(Boolean)
  } catch {
    // 普通文本按换行展示，避免在预览中暴露 JSON 字符串形式。
  }
  return value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
}

function isPreconditionField(key: string) {
  return ['precondition', 'preconditions', 'preCondition'].includes(key)
}

function isStepField(key: string) {
  return ['steps', 'test_steps', 'testSteps', 'operation'].includes(key)
}

function isExpectedField(key: string) {
  return ['expected_results', 'expectedResult', 'expectedResults', 'expected_result'].includes(key)
}

function FieldList({ lines, tone = 'default' }: { lines: string[]; tone?: 'default' | 'expected' }) {
  if (lines.length > 1) {
    return <ol className={cx(styles.fieldList, tone === 'expected' && styles.fieldListExpected)}>
      {lines.map((line, index) => <li key={`${index}-${line.slice(0, 8)}`}><span className={styles.fieldIndex}>{index + 1}.</span><span>{line}</span></li>)}
    </ol>
  }
  return <p className="m-0 whitespace-pre-wrap break-words text-[11px] leading-[1.65] text-app-surface-text-muted">{lines[0] || '-'}</p>
}

function DetailField({ field }: { field: GeneratedTestCase['detailFields'][number] }) {
  const expected = isExpectedField(field.key)
  const steps = isStepField(field.key)
  const precondition = isPreconditionField(field.key)
  return <section className={styles.cardSection}>
    <div className={cx(styles.sectionTitle, expected && styles.sectionTitleExpected)}>
      {expected ? <CheckCircleFilled aria-hidden /> : steps ? <PlayCircleOutlined aria-hidden /> : precondition ? <SnippetsOutlined aria-hidden /> : <FileTextOutlined aria-hidden />}
      <strong>{field.label}</strong>
    </div>
    <FieldList lines={fieldLines(field.value)} tone={expected ? 'expected' : 'default'} />
  </section>
}

function CaseEditor({ testCase, onChange }: { testCase: GeneratedTestCase; onChange: (patch: Record<string, unknown>) => void }) {
  const fields = getGeneratedCaseEditableFields(testCase)
  return <div className={styles.editor}>
    {fields.map(({ key, label }) => {
      const value = testCase.raw[key]
      const array = Array.isArray(value)
      const text = array ? value.join('\n') : String(value ?? '')
      return <label key={key} className={styles.editorField}>
        <span>{label}</span>
        <Input.TextArea
          aria-label={label}
          autoSize={{ minRows: 2, maxRows: 8 }}
          value={text}
          onChange={event => onChange({ [key]: array ? event.target.value.split('\n') : event.target.value })}
        />
      </label>
    })}
  </div>
}

function CaseDetailCard({ entry, editable, canDelete, onChangeCase, onDelete, onClose }: {
  entry: GeneratedCaseEntry
  editable: boolean
  canDelete: boolean
  onChangeCase?: (entry: GeneratedCaseEntry, patch: Record<string, unknown>) => void
  onDelete?: (entry: GeneratedCaseEntry) => void
  onClose: () => void
}) {
  const { testCase } = entry
  const tagFields = testCase.tagFields.filter(field => field.value)
  const hasTypeTag = tagFields.some(field => getTagKind(field.key) === 'type')
  const detailFields = testCase.detailFields.filter(field => !['test_model', 'testModel'].includes(field.key))
  return <article className={cx(styles.detailCard, 'nowheel', 'nodrag')} aria-label="用例详情">
    <div className={styles.detailHead}>
      <div className={styles.detailTags}>
        {tagFields.map((field) => {
          const kind = getTagKind(field.key)
          const toneClass = kind === 'id' ? styles.tagId : kind === 'type' ? styles.tagType : kind === 'priority' ? styles.tagPriority : undefined
      return <span key={field.key} title={kind === 'id' ? field.value : undefined} className={cx(styles.tag, toneClass)}>
            {kind === 'priority' && /^\d+$/.test(field.value) ? `P${field.value}` : field.value}
          </span>
        })}
        {!hasTypeTag ? <span className={cx(styles.tag, styles.tagType)}>{entry.caseType}</span> : null}
      </div>
      <span className="ml-auto inline-flex flex-none items-center gap-1">
        {editable ? <>
          {canDelete && onChangeCase ? <Button type="text" size="small" className={cx(styles.detailAction, styles.detailActionDanger)} icon={<DeleteOutlined aria-hidden />} title="删除用例" aria-label={`删除用例：${testCase.displayName}`} onClick={() => onDelete?.(entry)} /> : null}
          <Button type="text" size="small" className={styles.detailAction} icon={<CloseOutlined aria-hidden />} title="关闭用例详情" aria-label="关闭用例详情" onClick={onClose} />
        </> : <Button type="text" size="small" className={styles.detailAction} icon={<CloseOutlined aria-hidden />} title="关闭用例详情" aria-label="关闭用例详情" onClick={onClose} />}
      </span>
    </div>
    <p className={styles.breadcrumb}>{entry.moduleName} / {entry.caseType}</p>
    <h3 className={styles.detailTitle}>{testCase.displayName}</h3>
    {editable && onChangeCase
      ? <CaseEditor testCase={testCase} onChange={patch => onChangeCase(entry, patch)} />
      : <>
        {detailFields.map(field => <DetailField key={field.key} field={field} />)}
        <div className={styles.detailNote}><FileTextOutlined aria-hidden /><span>用例来自候选产物，采用前仍建议人工复核业务前提。</span></div>
      </>}
  </article>
}

type GraphActions = {
  onRootSelect: () => void
  onModuleSelect: (id: string) => void
  onSceneSelect: (id: string) => void
  onCaseSelect: (key: string) => void
  onCloseDetail: () => void
  onChangeCase?: (entry: GeneratedCaseEntry, patch: Record<string, unknown>) => void
  onDeleteCase?: (entry: GeneratedCaseEntry) => void
  canEdit: boolean
  canDelete: boolean
}

const GraphActionsContext = createContext<GraphActions | null>(null)

function useGraphActions() {
  const actions = useContext(GraphActionsContext)
  if (!actions) throw new Error('完整用例图谱缺少操作上下文')
  return actions
}

function TreeNode({ data }: { data: Extract<GeneratedCasesNodeData, { kind: 'root' | 'module' | 'scene' }> }) {
  const actions = useGraphActions()
  const className = data.kind === 'root'
    ? 'ai-case-name-tree-root'
    : `ai-case-name-tree-node ${data.kind === 'module' ? 'model' : 'test-model'}`
  const activate = () => {
    if (data.kind === 'root') actions.onRootSelect()
    else if (data.kind === 'module') actions.onModuleSelect(data.id)
    else actions.onSceneSelect(data.id)
  }
  return <>
    {data.kind !== 'root' ? <Handle type="target" position={Position.Left} className={workbenchStyles.handle} /> : null}
    <div className={cx(styles.treeNodeWrap, data.selected && styles.treeNodeWrapSelected)}>
      <div
        className={cx(className, 'cursor-pointer')}
        role="button"
        tabIndex={0}
        aria-pressed={data.selected}
        aria-expanded={data.kind === 'scene' ? data.expanded : undefined}
        aria-label={data.kind === 'root' ? `全部用例，${data.count} 个` : data.kind === 'module' ? `模块：${data.title}` : `用例类型：${data.title}，${data.count} 个用例`}
        title={data.kind === 'scene' ? `${data.title} · ${data.count} 个用例 · ${data.expanded ? '点击收起用例' : '点击展开用例'}` : `${data.title} · ${data.count} 个用例`}
        onClick={(event) => { event.stopPropagation(); activate() }}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); activate() } }}
      >
        <span className="ai-case-name-tree-node-label">{data.title}</span>
        {data.kind === 'scene' ? <span className="ml-1.5 inline-flex h-[17px] min-w-[17px] flex-none items-center justify-center rounded-full bg-app-surface px-1 text-[10px] font-semibold text-app-surface-text-muted">{data.count}</span> : null}
      </div>
    </div>
    <Handle type="source" position={Position.Right} className={workbenchStyles.handle} />
  </>
}

function CaseNode({ entry }: { entry: GeneratedCaseEntry }) {
  const actions = useGraphActions()
  return <>
    <Handle type="target" position={Position.Left} className={workbenchStyles.handle} />
    <div className={cx(styles.caseNodeWrap, styles.caseNodeShell, 'group relative')}>
      <div
        className={cx('ai-case-name-tree-node point', styles.caseNode)}
        role="button"
        tabIndex={0}
        aria-label={`用例：${entry.testCase.displayName}`}
        title={entry.testCase.displayName}
        onClick={(event) => { event.stopPropagation(); actions.onCaseSelect(entry.key) }}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); actions.onCaseSelect(entry.key) } }}
      >
        <span className={cx('ai-case-name-tree-node-label', workbenchStyles.pointName, actions.canDelete && 'pr-6')}>{entry.testCase.displayName}</span>
      </div>
      {actions.canDelete ? <Button
        type="text"
        size="small"
        className={cx(styles.caseDelete, 'nodrag')}
        icon={<DeleteOutlined aria-hidden />}
        title="删除用例"
        aria-label={`删除用例：${entry.testCase.displayName}`}
        onClick={(event) => { event.stopPropagation(); actions.onDeleteCase?.(entry) }}
      /> : null}
    </div>
  </>
}

function GeneratedCaseNode({ data }: NodeProps<GeneratedCasesFlowNode>) {
  const actions = useGraphActions()
  if (data.kind === 'root' || data.kind === 'module' || data.kind === 'scene') return <TreeNode data={data} />
  if (data.kind === 'case') return <CaseNode entry={data.entry} />
  return <>
    <Handle type="target" position={Position.Left} className={workbenchStyles.handle} />
    <CaseDetailCard
      entry={data.entry}
      editable={actions.canEdit}
      canDelete={actions.canDelete}
      onChangeCase={actions.onChangeCase}
      onDelete={actions.onDeleteCase}
      onClose={actions.onCloseDetail}
    />
  </>
}

const nodeTypes = { 'generated-case': GeneratedCaseNode }

function nodeWidth(data: GeneratedCasesNodeData) {
  if (data.kind === 'root') return 220
  if (data.kind === 'module') return 180
  if (data.kind === 'scene') return 170
  if (data.kind === 'case') return 360
  return 430
}

export type GeneratedCasesGraphHandle = {
  saveImage: () => Promise<void>
  fitView: () => void
}

type GeneratedCasesGraphProps = {
  model: GeneratedCasesModel
  selection: GeneratedCasesSelection
  expandedSceneIds: ReadonlySet<string>
  rootTitle: string
  focusKey?: string
  focusTick?: number
  canEdit: boolean
  canDelete: boolean
  onChangeCase?: (entry: GeneratedCaseEntry, patch: Record<string, unknown>) => void
  onDeleteCase?: (entry: GeneratedCaseEntry) => void
  onSelect: (selection: GeneratedCasesSelection) => void
  onSceneSelect: (sceneId: string) => void
  onModuleSelect: (moduleId: string) => void
  onCloseDetail: () => void
}

export const GeneratedCasesGraph = forwardRef<GeneratedCasesGraphHandle, GeneratedCasesGraphProps>(function GeneratedCasesGraph({ model, selection, expandedSceneIds, rootTitle, focusKey, focusTick = 0, canEdit, canDelete, onChangeCase, onDeleteCase, onSelect, onSceneSelect, onModuleSelect, onCloseDetail }, ref) {
  const graph = useMemo(() => buildGeneratedCasesGraph({ model, rootTitle, expandedSceneIds, selection }), [expandedSceneIds, model, rootTitle, selection])
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<GeneratedCasesFlowNode, GeneratedCasesFlowEdge> | null>(null)
  const [canvasSize, setCanvasSize] = useState<{ width: number; height: number } | null>(null)
  const [fitTick, setFitTick] = useState(0)

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
    const stageHeight = Math.max(graph.stageHeight, 1)
    const fit = fitTick > 0
    if (fit) {
      const zoom = Math.min(1, Math.max(0.25, Math.min((canvasSize.width - 32) / GENERATED_CASES_STAGE_WIDTH, (canvasSize.height - 32) / stageHeight)))
      return {
        x: Math.max(16, (canvasSize.width - GENERATED_CASES_STAGE_WIDTH * zoom) / 2),
        y: Math.max(16, (canvasSize.height - stageHeight * zoom) / 2),
        zoom,
      }
    }
    const focusEntry = focusKey ? model.entryByKey.get(focusKey) : undefined
    const focusNode = focusEntry ? graph.nodes.find(node => node.id === generatedCaseNodeId(focusEntry)) : undefined
    if (focusNode) {
      // 详情态优先保证用例卡可读；画布足够宽时再回退到整图居中，保留左侧树形上下文。
      const zoom = Math.min(1, Math.max(0.85, (canvasSize.width - 48) / GENERATED_CASES_STAGE_WIDTH))
      const stageFits = GENERATED_CASES_STAGE_WIDTH * zoom <= canvasSize.width - 32
      const focusCenterX = focusNode.position.x + nodeWidth(focusNode.data) / 2
      return {
        x: stageFits ? Math.max(16, (canvasSize.width - GENERATED_CASES_STAGE_WIDTH * zoom) / 2) : canvasSize.width / 2 - focusCenterX * zoom,
        y: canvasSize.height / 2 - (focusNode.position.y + (focusNode.height ?? 40) / 2) * zoom,
        zoom,
      }
    }
    const zoom = Math.min(1, Math.max(0.25, Math.min((canvasSize.width - 32) / GENERATED_CASES_STAGE_WIDTH, (canvasSize.height - 32) / stageHeight)))
    return {
      x: Math.max(16, (canvasSize.width - GENERATED_CASES_STAGE_WIDTH * zoom) / 2),
      y: Math.max(16, (canvasSize.height - stageHeight * zoom) / 2),
      zoom,
    }
  }, [canvasSize, fitTick, focusKey, graph.nodes, graph.stageHeight, model.entryByKey])

  const actions = useMemo<GraphActions>(() => ({
    onRootSelect: () => onSelect({ kind: 'overview' }),
    onModuleSelect,
    onSceneSelect,
    onCaseSelect: (key) => onSelect({ kind: 'case', key }),
    onCloseDetail,
    onChangeCase,
    onDeleteCase,
    canEdit,
    canDelete,
  }), [canDelete, canEdit, onCloseDetail, onChangeCase, onDeleteCase, onModuleSelect, onSceneSelect, onSelect])

  useImperativeHandle(ref, () => ({
    saveImage: async () => {
      const canvas = canvasRef.current
      const flow = flowRef.current
      if (!canvas || !flow) throw new Error('图谱尚未准备完成')
      await saveFlowImage(canvas, flow.getNodes(), `${rootTitle || '完整用例'}-用例图谱.png`)
    },
    fitView: () => setFitTick(tick => tick + 1),
  }), [rootTitle])

  return <GraphActionsContext.Provider value={actions}>
    <div ref={canvasRef} className={workbenchStyles.canvas}>
      {defaultViewport ? <ReactFlow<GeneratedCasesFlowNode, GeneratedCasesFlowEdge>
        key={`${fitTick}-${focusTick}`}
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        defaultViewport={defaultViewport}
        onInit={(instance) => { flowRef.current = instance }}
        onPaneClick={onCloseDetail}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        minZoom={0.25}
        maxZoom={1.5}
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
