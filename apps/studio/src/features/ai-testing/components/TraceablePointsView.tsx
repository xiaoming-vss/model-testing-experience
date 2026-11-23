import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Empty, Modal } from 'antd'
import {
  CompressOutlined,
  DownOutlined,
  FileTextOutlined,
  MenuOutlined,
  MinusSquareOutlined,
  PictureOutlined,
  PlusSquareOutlined,
  RightOutlined,
  SearchOutlined,
  ShareAltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { ArtifactEvidence, ArtifactEvidenceItem, ArtifactEvidenceMissing, ArtifactRefChips } from '@/shared/components/ArtifactView'
import { notify } from '@/shared/utils/toast'
import { cx } from '@/shared/utils/cx'
import { toRecordArray } from '@/shared/utils/value'
import { toDisplayText } from '../utils/functionalOutput'
import { buildTraceablePointsModel, TRACEABLE_REF_FIELDS, type TraceableGap, type TraceableIssue, type TraceablePoint } from '../utils/traceablePointsModel'
import type { TraceableSelection } from '../utils/traceablePointsGraph'
import { TraceablePointsGraph, type TraceableEvidenceRequest, type TraceablePointsGraphHandle } from './TraceablePointsGraph'
import { MaterialBlockContent, type MaterialBlock } from './ReadableRequirementMaterial'
import caseArtifactStyles from '../styles/artifact-cases.module.css'
import styles from '../styles/traceable-points.module.css'

type Props = {
  content: string
  onChange?: (content: string) => void
  materialContent?: string
  rootTitle?: string
}

type Page = 'points' | 'issues' | 'gaps'

const PAGE_LABEL: Record<Page, string> = { points: '测试点', issues: '审查', gaps: '缺口' }

function isEditableTarget(target: EventTarget | null) {
  return target instanceof HTMLElement
    && (target.matches('input, textarea, select') || target.isContentEditable)
}

function isRailOverlay() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(max-width: 1180px)').matches
}

function reviewTone(label: string) {
  if (label === '独立审查通过') return 'border-[var(--app-status-approved-border)] bg-[var(--app-status-approved-bg)] text-app-status-approved-text'
  if (label === '独立审查未通过') return 'border-app-request-error-border bg-app-danger-surface-soft text-app-request-error-text'
  return 'border-app-status-warning-border bg-app-status-warning-bg text-app-status-warning-text'
}

const ISSUE_KIND_LABEL: Record<string, string> = {
  unsupported: '依据不足',
  missing: '遗漏',
  granularity: '粒度过粗',
  classification: '分类问题',
}

function issueTargetLabel(issue: TraceableIssue, point?: TraceablePoint, gap?: TraceableGap) {
  if (point) return point.name
  if (gap) return gap.id
  if (issue.targetType === 'missing' || !issue.targetId) return '遗漏项'
  return issue.targetType === 'coverageGap' ? '未定位的覆盖缺口' : '未定位的测试点'
}

function EvidenceItems({ blockIds, blockById, sourceById }: {
  blockIds: string[]
  blockById: Map<string, Record<string, unknown>>
  sourceById: Map<string, Record<string, unknown>>
}) {
  return <>{blockIds.map((id) => {
    const block = blockById.get(id)
    if (!block) return <ArtifactEvidenceMissing key={id}>{id}：未找到对应材料</ArtifactEvidenceMissing>
    const source = sourceById.get(toDisplayText(block.sourceId))
    return <ArtifactEvidenceItem key={id} source={toDisplayText(source?.name) || '来源未找到'} locator={toDisplayText(block.locator)}>
      <MaterialBlockContent block={block as MaterialBlock} />
    </ArtifactEvidenceItem>
  })}</>
}

export function TraceablePointsView({ content, onChange, materialContent, rootTitle = '测试点' }: Props) {
  const [page, setPage] = useState<Page>('points')
  const [query, setQuery] = useState('')
  const [selection, setSelection] = useState<TraceableSelection>({ kind: 'overview' })
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(() => new Set())
  const [collapsedModules, setCollapsedModules] = useState<Set<string>>(() => new Set())
  const [railOpen, setRailOpen] = useState(false)
  const [evidence, setEvidence] = useState<TraceableEvidenceRequest | null>(null)
  const [savingImage, setSavingImage] = useState(false)
  const searchRef = useRef<HTMLInputElement | null>(null)
  const graphRef = useRef<TraceablePointsGraphHandle | null>(null)

  const model = useMemo(() => buildTraceablePointsModel(content, materialContent), [content, materialContent])
  const sceneIds = useMemo(() => model?.modules.flatMap(module => module.scenes.map(scene => scene.id)) ?? [], [model])
  const allExpanded = sceneIds.length > 0 && sceneIds.every(id => expandedScenes.has(id))
  const activeIssue = model?.issues.length
    ? (selection.kind === 'issue' ? (model.issues[selection.index] ?? model.issues[0]) : model.issues[0])
    : undefined
  const activeGap = model?.gaps.length
    ? (selection.kind === 'gap' ? (model.gaps.find(gap => gap.id === selection.id) ?? model.gaps[0]) : model.gaps[0])
    : undefined
  const issueGap = activeIssue?.gapId ? model?.gaps.find(gap => gap.id === activeIssue.gapId) : undefined
  const graphGap = page === 'gaps' ? activeGap : issueGap

  const closeRail = useCallback(() => {
    if (isRailOverlay()) setRailOpen(false)
  }, [])

  const selectPage = (next: Page) => {
    setPage(next)
    setQuery('')
    if (next === 'gaps') setSelection(model?.gaps.length ? { kind: 'gap', id: model.gaps[0].id } : { kind: 'overview' })
    else if (next === 'issues') setSelection(model?.issues.length ? { kind: 'issue', index: 0 } : { kind: 'overview' })
    else setSelection({ kind: 'overview' })
  }

  const findPoint = useCallback((pointId: string) => {
    const point = model?.pointById.get(pointId)
    if (!point) return
    setExpandedScenes((current) => new Set(current).add(point.sceneId))
    setPage('points')
    setSelection({ kind: 'point', id: point.id })
    setQuery('')
    closeRail()
  }, [closeRail, model])

  const selectFromGraph = useCallback((next: TraceableSelection) => {
    if (next.kind === 'point') {
      const point = model?.pointById.get(next.id)
      if (point) setExpandedScenes((current) => new Set(current).add(point.sceneId))
    }
    setSelection(next)
  }, [model])

  const toggleScene = useCallback((sceneId: string) => {
    setExpandedScenes((current) => {
      const next = new Set(current)
      if (next.has(sceneId)) next.delete(sceneId)
      else next.add(sceneId)
      return next
    })
    setSelection({ kind: 'scene', id: sceneId })
    closeRail()
  }, [closeRail])

  const resetSelection = () => {
    setQuery('')
    if (page === 'gaps' && model?.gaps.length) setSelection({ kind: 'gap', id: model.gaps[0].id })
    else if (page === 'issues' && model?.issues.length) setSelection({ kind: 'issue', index: 0 })
    else setSelection({ kind: 'overview' })
  }

  const toggleAll = () => {
    setExpandedScenes(allExpanded ? new Set() : new Set(sceneIds))
    setSelection({ kind: 'overview' })
  }

  const updateName = useCallback((pointId: string, name: string) => {
    if (!onChange || !model) return
    const point = model.pointById.get(pointId)
    if (!point?.rawId) return
    const next = {
      ...model.artifact,
      reviewStatus: 'self_review_only',
      testPoints: toRecordArray(model.artifact.testPoints).map(entry => (
        toDisplayText(entry.id) === point.rawId ? { ...entry, name } : entry
      )),
    }
    onChange(JSON.stringify(next, null, 2))
  }, [model, onChange])

  const saveImage = async () => {
    if (!graphRef.current) return
    setSavingImage(true)
    try {
      await graphRef.current.saveImage()
      notify.success('图片已保存')
    } catch {
      notify.error('图片导出失败，请重试')
    } finally {
      setSavingImage(false)
    }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === '/' && !isEditableTarget(event.target)) {
        event.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      }
      if (event.key === 'Escape') {
        if (document.activeElement === searchRef.current) {
          setQuery('')
          searchRef.current?.blur()
        } else if (railOpen) {
          setRailOpen(false)
        }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [railOpen])

  if (!model) {
    return <div className="flex min-h-0 flex-1 items-center justify-center bg-app-surface p-6"><Empty description="测试点格式无效，请重新生成" /></div>
  }

  const normalizedQuery = query.trim().toLowerCase()
  const matchingPoints = normalizedQuery
    ? model.points.filter(point => `${point.id} ${point.name} ${point.module} ${point.scene}`.toLowerCase().includes(normalizedQuery))
    : []
  const matchingGaps = normalizedQuery
    ? model.gaps.filter(gap => `${gap.id} ${gap.description} ${gap.blockedCoverage}`.toLowerCase().includes(normalizedQuery))
    : model.gaps
  const matchingIssues = normalizedQuery
    ? model.issues.filter((issue) => {
      const point = issue.pointId ? model.pointById.get(issue.pointId) : undefined
      const gap = issue.gapId ? model.gaps.find(entry => entry.id === issue.gapId) : undefined
      return `${issue.issue} ${issue.suggestion} ${issue.kind} ${issueTargetLabel(issue, point, gap)}`.toLowerCase().includes(normalizedQuery)
    })
    : model.issues

  const selectedPoint = selection.kind === 'point' ? model.pointById.get(selection.id) : undefined
  const selectedModule = selection.kind === 'module' ? model.modules.find(module => module.id === selection.id) : undefined
  const selectedScene = selection.kind === 'scene' ? model.sceneById.get(selection.id) : undefined
  const selectedIssuePoint = activeIssue?.pointId ? model.pointById.get(activeIssue.pointId) : undefined
  const selectedIssueGap = activeIssue?.gapId ? model.gaps.find(gap => gap.id === activeIssue.gapId) : undefined

  const focus = (() => {
    if (normalizedQuery) {
      const count = page === 'points' ? matchingPoints.length : page === 'gaps' ? matchingGaps.length : matchingIssues.length
      return { label: `搜索 “${query.trim()}”`, meta: '搜索', count }
    }
    if (page === 'gaps' && activeGap) return { label: activeGap.description, meta: '覆盖缺口', count: activeGap.relatedPointIds.length }
    if (page === 'issues') {
      if (!activeIssue) return { label: '审查结果', meta: '审查', count: model.issues.length }
      return { label: issueTargetLabel(activeIssue, selectedIssuePoint, selectedIssueGap), meta: '审查问题', count: model.issues.length }
    }
    if (selectedPoint) return { label: selectedPoint.name, meta: '测试点', count: selectedPoint.refCount }
    if (selectedScene) return { label: selectedScene.title, meta: '场景', count: selectedScene.points.length }
    if (selectedModule) return { label: selectedModule.title, meta: '模块', count: selectedModule.points.length }
    return { label: '全部测试点', meta: '模块', count: model.points.length }
  })()

  const reviewToneClass = reviewTone(model.reviewLabel)
  const sceneCount = model.modules.reduce((sum, module) => sum + module.scenes.length, 0)
  const railTitle = normalizedQuery ? '搜索结果' : page === 'points' ? '覆盖索引' : page === 'gaps' ? '覆盖缺口' : '审查问题'
  const railCount = normalizedQuery
    ? page === 'points' ? matchingPoints.length : page === 'gaps' ? matchingGaps.length : matchingIssues.length
    : page === 'points' ? sceneCount : page === 'gaps' ? model.gaps.length : model.issues.length
  const railSubtitle = normalizedQuery
    ? page === 'points'
      ? `${matchingPoints.length} 个匹配测试点`
      : page === 'gaps'
        ? `${matchingGaps.length} 个匹配缺口`
        : `${matchingIssues.length} 个匹配审查问题`
    : page === 'points'
      ? `${model.modules.length} 个模块 · ${sceneCount} 个场景 · ${model.points.length} 个测试点`
      : page === 'gaps'
        ? `${model.gaps.length} 个缺口 · ${new Set(model.gaps.flatMap(gap => gap.relatedPointIds)).size} 个关联测试点`
        : `${model.issues.length} 个未解决问题 · ${model.reviewLabel}`
  const activeSceneId = selectedPoint?.sceneId ?? selectedScene?.id
  const allRailCollapsed = model.modules.length > 0 && model.modules.every(module => collapsedModules.has(module.id))

  const toggleRailModules = () => {
    setCollapsedModules(allRailCollapsed ? new Set() : new Set(model.modules.map(module => module.id)))
  }

  return <div className={cx('flex min-h-0 flex-1 flex-col overflow-hidden bg-app-surface', caseArtifactStyles.scope)}>
    <header className="flex flex-none flex-wrap items-center gap-x-3 gap-y-2 border-b border-app-surface-border px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        <span className="inline-flex size-6 flex-none items-center justify-center rounded-[6px] border border-app-surface-border bg-app-surface-hover text-app-accent" aria-hidden><ShareAltOutlined /></span>
        <h1 className="m-0 truncate text-[13px] font-semibold text-app-surface-text">测试点图谱</h1>
        <span className="inline-flex h-[20px] min-w-[20px] items-center justify-center rounded-full bg-app-surface-hover px-1.5 font-mono text-[10px] text-app-surface-text-muted">{model.points.length}</span>
        <span className={cx('inline-flex h-[21px] max-w-full items-center gap-1 truncate rounded-[5px] border px-1.5 text-[10.5px]', reviewToneClass)}>
          <i className="size-1.5 flex-none rounded-full bg-current" aria-hidden />
          {model.reviewLabel}
        </span>
      </div>

      <div className="flex items-stretch gap-0.5 max-narrow-sm:order-last max-narrow-sm:w-full" role="tablist" aria-label="测试点视图">
        {(['points', 'issues', 'gaps'] as const).map((key) => {
          const active = page === key
          const count = key === 'points' ? model.points.length : key === 'issues' ? model.issues.length : model.gaps.length
          const warning = key === 'issues' ? count > 0 : key === 'gaps' ? count > 0 : false
          return <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active}
            className={cx('relative inline-flex h-[34px] cursor-pointer items-center gap-1.5 border-0 bg-transparent px-2 text-[11.5px] text-app-surface-text-muted hover:text-app-surface-text', active && styles.tabActive)}
            onClick={() => selectPage(key)}
          >
            {PAGE_LABEL[key]}
            <span className={cx('inline-grid h-[18px] min-w-[18px] place-items-center rounded-full px-[5px] text-[9.5px] font-semibold', warning ? 'bg-app-status-warning-bg text-app-status-warning-text' : 'bg-app-surface-hover text-app-surface-text-muted')}>{count}</span>
          </button>
        })}
      </div>

      <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-1.5 max-narrow-sm:w-full max-narrow-sm:justify-start">
        <button type="button" className="hidden size-7 cursor-pointer items-center justify-center rounded-[6px] border border-app-surface-border bg-app-surface text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text max-[1180px]:inline-flex" title="打开覆盖索引" aria-label="打开覆盖索引" onClick={() => setRailOpen(true)}><MenuOutlined aria-hidden /></button>
        <label className="relative flex h-7 w-[210px] max-w-full items-center max-narrow-sm:w-full">
          <SearchOutlined className="pointer-events-none absolute left-2 text-[12px] text-app-surface-text-muted" aria-hidden />
          <input
            ref={searchRef}
            value={query}
            onChange={(event) => {
              const next = event.target.value
              setQuery(next)
              if (next.trim() && isRailOverlay()) setRailOpen(true)
            }}
            className="h-7 w-full rounded-[6px] border border-app-surface-border bg-app-surface pl-7 pr-8 text-[11.5px] text-app-surface-text outline-none placeholder:text-app-surface-text-muted focus:border-app-accent-border focus:ring-2 focus:ring-app-accent-selection"
            aria-label={page === 'gaps' ? '搜索覆盖缺口' : page === 'issues' ? '搜索审查问题' : '搜索测试点、模块或场景'}
            placeholder={page === 'gaps' ? '搜索覆盖缺口' : page === 'issues' ? '搜索审查问题' : '搜索测试点、模块或场景'}
          />
          <kbd className="pointer-events-none absolute right-1.5 rounded-[3px] border border-app-surface-border bg-app-surface-hover px-1 font-mono text-[9.5px] leading-[1.5] text-app-surface-text-muted">/</kbd>
        </label>
        <ProjectActionButton action="write" size="small" icon={<PictureOutlined aria-hidden />} loading={savingImage} onClick={() => void saveImage()}>保存图片</ProjectActionButton>
      </div>
    </header>

    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <aside className={cx(styles.rail, 'flex h-full w-[300px] flex-none flex-col border-r border-app-surface-border max-[1360px]:w-[272px] max-[1180px]:w-[300px]', railOpen && styles.railOpen)} aria-label="测试点覆盖索引">
        <div className="flex flex-none flex-col gap-1 px-3 pb-2 pt-3.5">
          <div className="flex items-center gap-2">
            <h2 className="m-0 text-[12px] font-semibold text-app-surface-text">{railTitle}</h2>
            <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-app-surface-hover px-1.5 font-mono text-[9.5px] text-app-surface-text-muted">{railCount}</span>
            <span className="ml-auto inline-flex items-center gap-0.5">
              {page === 'points' && !normalizedQuery && model.modules.length
                ? <button type="button" className="inline-flex size-6 cursor-pointer items-center justify-center rounded-[5px] border-0 bg-transparent text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text" title={allRailCollapsed ? '展开索引列表' : '折叠索引列表'} aria-label={allRailCollapsed ? '展开索引列表' : '折叠索引列表'} onClick={toggleRailModules}>{allRailCollapsed ? <RightOutlined aria-hidden /> : <DownOutlined aria-hidden />}</button>
                : null}
              <button type="button" className="hidden size-6 cursor-pointer items-center justify-center rounded-[5px] border-0 bg-transparent text-[15px] leading-none text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text max-[1180px]:inline-flex" title="关闭覆盖索引" aria-label="关闭覆盖索引" onClick={() => setRailOpen(false)}><span aria-hidden>×</span></button>
            </span>
          </div>
          <p className="m-0 text-[11px] leading-[1.45] text-app-surface-text-muted">{railSubtitle}</p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {page === 'points' && normalizedQuery
            ? (matchingPoints.length
              ? <div className="flex flex-col gap-0.5">{matchingPoints.map(point => <button key={point.id} type="button" className="flex w-full cursor-pointer flex-col gap-0.5 rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left hover:bg-app-surface focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-app-accent" onClick={() => findPoint(point.id)}>
                <span className="line-clamp-2 text-[11.5px] leading-[1.35] text-app-surface-text [overflow-wrap:anywhere]">{point.name}</span>
                <span className="text-[10px] text-app-surface-text-muted">{point.module} · {point.scene}</span>
              </button>)}</div>
              : <div className="flex flex-col items-center gap-1 px-3 py-10 text-center text-app-surface-text-muted"><SearchOutlined aria-hidden /><strong className="text-[11.5px] text-app-surface-text">没有匹配的测试点</strong><span className="text-[11px] leading-[1.5]">试试模块名、场景名或测试点编号。</span></div>)
            : page === 'points'
              ? <div className="flex flex-col gap-0.5">{model.modules.map(module => {
                const collapsed = collapsedModules.has(module.id)
                return <div key={module.id}>
                  <button type="button" className={cx('flex w-full cursor-pointer items-center gap-1.5 rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left text-[11.5px] text-app-surface-text hover:bg-app-surface', selection.kind === 'module' && selection.id === module.id && 'bg-app-accent-selection ring-1 ring-inset ring-app-accent-border')} aria-expanded={!collapsed} onClick={() => { setCollapsedModules(current => { const next = new Set(current); if (next.has(module.id)) next.delete(module.id); else next.add(module.id); return next }); setSelection({ kind: 'module', id: module.id }) }}>
                    {collapsed ? <RightOutlined className="text-[9px] text-app-surface-text-muted" aria-hidden /> : <DownOutlined className="text-[9px] text-app-surface-text-muted" aria-hidden />}
                    <span className="min-w-0 flex-1 truncate font-semibold">{module.title}</span>
                    <span className="font-mono text-[9.5px] text-app-surface-text-muted">{module.points.length}</span>
                  </button>
                  {collapsed ? null : <div className="ml-2.5 border-l border-app-surface-border pl-1.5">{module.scenes.map(scene => <button key={scene.id} type="button" className={cx('flex w-full cursor-pointer items-center gap-1.5 rounded-[5px] border-0 bg-transparent px-1.5 py-1 text-left text-[11px] text-app-surface-text-muted hover:bg-app-surface hover:text-app-surface-text', activeSceneId === scene.id && 'bg-app-accent-selection text-app-surface-text ring-1 ring-inset ring-app-accent-border')} onClick={() => toggleScene(scene.id)} title={`${scene.title} · ${scene.points.length} 个测试点`}>
                    <i className="size-[5px] flex-none rounded-full bg-[var(--app-graph-edge-reference)]" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{scene.title}</span>
                    <span className="font-mono text-[9.5px]">{scene.points.length}</span>
                  </button>)}</div>}
                </div>
              })}</div>
              : page === 'gaps'
                ? (matchingGaps.length
                  ? <div className="flex flex-col gap-0.5">{matchingGaps.map(gap => <button key={gap.id} type="button" className={cx('flex w-full cursor-pointer flex-col gap-0.5 rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left hover:bg-app-surface', activeGap?.id === gap.id && 'bg-app-status-warning-bg ring-1 ring-inset ring-app-status-warning-border')} onClick={() => { setSelection({ kind: 'gap', id: gap.id }); closeRail() }}>
                    <span className="flex items-center gap-1.5"><span className="font-mono text-[9.5px] text-app-status-warning-text">{gap.id}</span><span className="text-[9.5px] text-app-surface-text-muted">{gap.relatedPointIds.length} 个关联测试点</span></span>
                    <span className="line-clamp-2 text-[11.5px] leading-[1.35] text-app-surface-text [overflow-wrap:anywhere]">{gap.description}</span>
                  </button>)}</div>
                  : <div className="px-3 py-10 text-center text-[11px] text-app-surface-text-muted">没有匹配的缺口</div>)
                : page === 'issues'
                  ? (!activeIssue
                    ? <div className="m-1 rounded-[8px] border border-[var(--app-status-approved-border)] bg-[var(--app-status-approved-bg)] p-3">
                      <strong className="flex items-center gap-1.5 text-[11px] text-app-status-approved-text"><span aria-hidden>✓</span>{model.reviewLabel === '独立审查通过' ? '独立审查通过' : '没有未解决的审查问题'}</strong>
                      <p className="m-0 mt-1.5 text-[11px] leading-[1.5] text-app-surface-text-muted">当前产物没有记录阻断、重要或次要审查问题。审查结果仅供人工判断。</p>
                    </div>
                    : matchingIssues.length
                      ? <div className="flex flex-col gap-0.5">{matchingIssues.map(issue => {
                        const point = issue.pointId ? model.pointById.get(issue.pointId) : undefined
                        const gap = issue.gapId ? model.gaps.find(entry => entry.id === issue.gapId) : undefined
                        return <button key={issue.index} type="button" className={cx('flex w-full cursor-pointer flex-col gap-0.5 rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left hover:bg-app-surface', activeIssue?.index === issue.index && 'bg-app-danger-surface-soft ring-1 ring-inset ring-app-request-error-border')} onClick={() => { setSelection({ kind: 'issue', index: issue.index }); closeRail() }}>
                          <span className="flex items-center gap-1.5"><span className="rounded-[3px] border border-app-request-error-border px-1 text-[9.5px] text-app-request-error-text">{ISSUE_KIND_LABEL[issue.kind] ?? '审查问题'}</span><span className="truncate text-[9.5px] text-app-surface-text-muted">{issueTargetLabel(issue, point, gap)}</span></span>
                          <span className="line-clamp-2 text-[11.5px] leading-[1.35] text-app-surface-text [overflow-wrap:anywhere]">{issue.issue}</span>
                        </button>
                      })}</div>
                      : <div className="px-3 py-10 text-center text-[11px] text-app-surface-text-muted">没有匹配的审查问题</div>)
                  : null}
        </div>

        <footer className="flex flex-none flex-wrap items-center gap-x-2 gap-y-1 border-t border-app-surface-border px-3 py-2 text-[10.5px] text-app-surface-text-muted">
          <span className={cx('inline-flex h-[21px] items-center gap-1 rounded-[5px] border px-1.5', reviewToneClass)}><i className="size-1.5 rounded-full bg-current" aria-hidden />{model.reviewLabel}</span>
          <span className="ml-auto inline-flex items-center gap-1"><FileTextOutlined aria-hidden />只读产物</span>
        </footer>
      </aside>

      {railOpen ? <div className={styles.backdrop} aria-hidden onClick={() => setRailOpen(false)} /> : null}

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col" aria-label="测试点图谱">
        <TraceablePointsGraph
          ref={graphRef}
          model={model}
          mode={page}
          query={query}
          selection={selection}
          expandedSceneIds={expandedScenes}
          activeGap={graphGap}
          activeIssue={page === 'issues' ? activeIssue : undefined}
          rootTitle={rootTitle}
          canRenamePoints={Boolean(onChange)}
          onSelect={selectFromGraph}
          onSceneSelect={toggleScene}
          onFindPoint={findPoint}
          onRenamePoint={updateName}
          onOpenEvidence={setEvidence}
        />

        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-wrap items-start gap-2 p-3">
          <button type="button" className="pointer-events-auto inline-flex max-w-[min(420px,calc(100%-8px))] shrink-0 cursor-pointer items-center gap-1.5 rounded-[7px] border border-app-surface-border bg-app-surface px-2.5 py-1.5 text-[11px] text-app-surface-text hover:border-app-accent-border" title="回到总览" onClick={resetSelection}>
            <span className="shrink-0 font-semibold text-app-accent">{focus.meta}</span>
            <span className="min-w-0 truncate">{focus.label}</span>
            <span className="shrink-0 rounded-[3px] bg-app-surface-hover px-1 font-mono text-[9.5px] text-app-surface-text-muted">{focus.count}</span>
          </button>
          <div className="pointer-events-auto ml-auto flex items-center gap-1.5">
            {page === 'points' && !normalizedQuery
              ? <button type="button" className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[10.5px] text-app-surface-text hover:border-app-accent-border hover:bg-app-surface-hover" aria-pressed={allExpanded} onClick={toggleAll}>
                {allExpanded ? <MinusSquareOutlined aria-hidden /> : <PlusSquareOutlined aria-hidden />}
                {allExpanded ? '收起全部' : '全部展开'}
              </button>
              : null}
            <button type="button" className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[10.5px] text-app-surface-text-muted hover:border-app-accent-border hover:bg-app-surface-hover hover:text-app-surface-text" title="适应画布" aria-label="适应画布" onClick={() => graphRef.current?.fitView()}><CompressOutlined aria-hidden />适应画布</button>
          </div>
        </div>

        <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex items-center gap-3 rounded-[6px] border border-app-surface-border bg-app-surface px-2.5 py-1.5 text-[10px] text-app-surface-text-muted" aria-label="图例">
          <span className="inline-flex items-center gap-1"><i className="size-1.5 rounded-full bg-[var(--app-graph-edge-primary)]" aria-hidden />模块</span>
          <span className="inline-flex items-center gap-1"><i className="size-1.5 rounded-full bg-[var(--app-graph-edge-reference)]" aria-hidden />场景</span>
          <span className="inline-flex items-center gap-1"><i className="size-[7px] rounded-full border border-app-status-warning-text" aria-hidden />缺口关联</span>
        </div>
        <span className="pointer-events-none absolute bottom-3 right-3 z-10 text-[10px] text-app-surface-text-muted">滚轮浏览 · Ctrl + 滚轮缩放</span>
      </main>
    </div>

    <Modal
      open={Boolean(evidence)}
      title={evidence ? <span className="flex flex-col gap-0.5"><span className="text-[10px] font-normal tracking-[0.04em] text-app-surface-text-muted">材料依据</span><span className="text-[13px] font-semibold text-app-surface-text">{evidence.title}</span></span> : null}
      footer={null}
      width={760}
      centered
      destroyOnHidden
      onCancel={() => setEvidence(null)}
      styles={{ body: { maxHeight: '68vh', overflowY: 'auto' } }}
    >
      {evidence ? <div className="flex flex-col gap-4">
        <ArtifactEvidence title="材料依据" count={evidence.blockIds.length}>
          <EvidenceItems blockIds={evidence.blockIds} blockById={model.blockById} sourceById={model.sourceById} />
        </ArtifactEvidence>
        {evidence.refs ? TRACEABLE_REF_FIELDS.filter(item => item.field !== 'materialBlockIds' && evidence.refs?.[item.field].length).map(item => (
          <ArtifactRefChips key={item.field} title={item.label} values={evidence.refs?.[item.field] ?? []} />
        )) : null}
        {evidence.refs?.riskIds.length ? <div className="flex items-start gap-1.5 rounded-[6px] border border-app-status-warning-border bg-app-status-warning-bg px-2 py-1.5 text-[10.5px] leading-[1.5] text-app-surface-text"><WarningOutlined className="mt-px shrink-0 text-app-status-warning-text" aria-hidden />引用只证明关联，不自动证明语义正确。</div> : null}
      </div> : null}
    </Modal>
  </div>
}
