import { CompressOutlined, DownOutlined, FileTextOutlined, MenuOutlined, MinusSquareOutlined, PictureOutlined, PlusSquareOutlined, RightOutlined } from '@ant-design/icons'
import { Empty } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { notify } from '@/shared/utils/toast'
import { cx } from '@/shared/utils/cx'
import { isRailOverlayViewport } from '@/shared/utils/viewport'
import { isJsonText } from '../utils/functionalOutput'
import {
  buildGeneratedCasesModel,
  type GeneratedCaseEntry,
  type GeneratedCasesModel,
} from '../utils/generatedCasesModel'
import type { GeneratedCasesSelection } from '../utils/generatedCasesGraph'
import { GeneratedCasesGraph, type GeneratedCasesGraphHandle } from './GeneratedCasesGraph'
import workbenchStyles from '../styles/traceable-points.module.css'
import artifactStyles from '../styles/artifact-cases.module.css'

type Props = {
  content: string
  onChange?: (content: string) => void
  /** 删除测试点只在候选草稿工作台开启；版本阅读弹窗只读展示。 */
  allowDelete?: boolean
  rootTitle?: string
  selectedCaseKey?: string
  onCaseSelect?: (key: string, raw: Record<string, unknown>) => void
}

const PAGE_LABEL = '用例索引'

const INLINE_GAP = 'inline-flex items-center gap-1'
const RAIL_LIST = 'flex flex-col gap-0.5'
const FLEX_TRUNCATE = 'min-w-0 flex-1 truncate'
const CHEVRON = 'text-[9px] text-app-surface-text-muted'
const HEADER_GROUP = 'flex items-center gap-2'
const FOCUS_LABEL = 'min-w-0 truncate'

function sceneIdsOf(model: GeneratedCasesModel) {
  return model.modules.flatMap(module => module.scenes.map(scene => scene.id))
}

function scenesOfModule(module: GeneratedCasesModel['modules'][number]) {
  return module.scenes.map(scene => scene.id)
}

export function GeneratedCasesReviewView({
  content,
  onChange,
  allowDelete = false,
  rootTitle = '完整用例',
  selectedCaseKey,
  onCaseSelect,
}: Props) {
  const model = useMemo(() => buildGeneratedCasesModel(content), [content])
  const [selection, setSelection] = useState<GeneratedCasesSelection>({ kind: 'overview' })
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(() => new Set())
  const [collapsedModules, setCollapsedModules] = useState<Set<string>>(() => new Set())
  const [railOpen, setRailOpen] = useState(false)
  const [savingImage, setSavingImage] = useState(false)
  const [focusTick, setFocusTick] = useState(0)
  const graphRef = useRef<GeneratedCasesGraphHandle | null>(null)
  const autoSelectedEdit = useRef(false)

  const allSceneIds = useMemo(() => (model ? sceneIdsOf(model) : []), [model])
  const allExpanded = allSceneIds.length > 0 && allSceneIds.every(id => expandedScenes.has(id))
  const activeEntry = selection.kind === 'case' && model ? model.entryByKey.get(selection.key) : undefined
  const activeScene = activeEntry && model ? model.sceneByEntryKey.get(activeEntry.key) : undefined
  const canEdit = Boolean(onChange)
  const canDelete = Boolean(onChange && allowDelete)

  const closeRail = useCallback(() => {
    if (isRailOverlayViewport()) setRailOpen(false)
  }, [])

  const selectEntry = useCallback((entry: GeneratedCaseEntry, modelForScene: GeneratedCasesModel | null = model, options: { focus?: boolean } = {}) => {
    if (!modelForScene) return
    const scene = modelForScene.sceneByEntryKey.get(entry.key)
    if (scene) setExpandedScenes(current => new Set(current).add(scene.id))
    setSelection({ kind: 'case', key: entry.key })
    closeRail()
    onCaseSelect?.(entry.key, entry.testCase.raw)
    if (options.focus) setFocusTick(tick => tick + 1)
  }, [closeRail, model, onCaseSelect])

  useEffect(() => {
    if (autoSelectedEdit.current || !onChange || selectedCaseKey || !model?.entries.length) return
    autoSelectedEdit.current = true
    selectEntry(model.entries[0], model)
    setFocusTick(tick => tick + 1)
  }, [model, onChange, selectEntry, selectedCaseKey])

  useEffect(() => {
    if (!selectedCaseKey || !model) return
    const entry = model.entryByKey.get(selectedCaseKey)
    if (!entry) return
    const scene = model.sceneByEntryKey.get(entry.key)
    if (scene) setExpandedScenes(current => new Set(current).add(scene.id))
    setSelection({ kind: 'case', key: entry.key })
    setFocusTick(tick => tick + 1)
  }, [model, selectedCaseKey])

  useEffect(() => {
    if (!model || selection.kind !== 'case' || model.entryByKey.has(selection.key)) return
    setSelection({ kind: 'overview' })
  }, [model, selection])

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

  const toggleModule = useCallback((module: GeneratedCasesModel['modules'][number]) => {
    const ids = scenesOfModule(module)
    setExpandedScenes((current) => {
      const next = new Set(current)
      const allOn = ids.length > 0 && ids.every(id => next.has(id))
      ids.forEach((id) => {
        if (allOn) next.delete(id)
        else next.add(id)
      })
      return next
    })
    setSelection({ kind: 'module', id: module.id })
    closeRail()
  }, [closeRail])

  const selectFromGraph = useCallback((next: GeneratedCasesSelection) => {
    if (next.kind === 'case' && model) {
      const entry = model.entryByKey.get(next.key)
      if (entry) {
        const scene = model.sceneByEntryKey.get(entry.key)
        if (scene) setExpandedScenes(current => new Set(current).add(scene.id))
      }
    }
    setSelection(next)
  }, [model])

  const selectSceneFromGraph = useCallback((sceneId: string) => {
    toggleScene(sceneId)
  }, [toggleScene])

  const selectModuleFromGraph = useCallback((moduleId: string) => {
    const module = model?.modules.find(item => item.id === moduleId)
    if (module) toggleModule(module)
  }, [model, toggleModule])

  const resetSelection = () => {
    setSelection({ kind: 'overview' })
  }

  const toggleAll = () => {
    setExpandedScenes(allExpanded ? new Set() : new Set(allSceneIds))
    setSelection({ kind: 'overview' })
  }

  const updateCase = useCallback((entry: GeneratedCaseEntry, patch: Record<string, unknown>) => {
    if (!onChange) return
    const parsed: unknown = JSON.parse(content)
    const cases = Array.isArray(parsed) ? parsed : (parsed as { cases?: unknown[] } | null)?.cases
    if (!Array.isArray(cases) || !cases[entry.testCase.sourceIndex]) return
    const nextCases = cases.slice()
    nextCases[entry.testCase.sourceIndex] = { ...(nextCases[entry.testCase.sourceIndex] as Record<string, unknown>), ...patch }
    const next = Array.isArray(parsed) ? nextCases : { ...(parsed as Record<string, unknown>), cases: nextCases }
    onChange(JSON.stringify(next, null, 2))
  }, [content, onChange])

  const deleteCase = useCallback((entry: GeneratedCaseEntry) => {
    if (!onChange || !allowDelete || !model) return
    const parsed: unknown = JSON.parse(content)
    const cases = Array.isArray(parsed) ? parsed : (parsed as { cases?: unknown[] } | null)?.cases
    if (!Array.isArray(cases)) return
    const deletedIndex = entry.testCase.sourceIndex
    if (!cases[deletedIndex]) return
    const nextCases = cases.filter((_, index) => index !== deletedIndex)
    const next = Array.isArray(parsed) ? nextCases : { ...(parsed as Record<string, unknown>), cases: nextCases }
    const nextContent = JSON.stringify(next, null, 2)
    onChange(nextContent)

    const nextModel = buildGeneratedCasesModel(nextContent)
    if (!nextModel?.entries.length) {
      setSelection({ kind: 'overview' })
      return
    }
    const current = selection.kind === 'case' ? model.entryByKey.get(selection.key) : undefined
    let nextEntry: GeneratedCaseEntry | undefined
    if (current && current.key !== entry.key) {
      const targetIndex = current.testCase.sourceIndex > deletedIndex ? current.testCase.sourceIndex - 1 : current.testCase.sourceIndex
      nextEntry = nextModel.entries.find(item => item.testCase.sourceIndex === targetIndex
        && item.moduleName === current.moduleName
        && item.caseType === current.caseType)
    }
    if (!nextEntry) {
      const position = model.entries.findIndex(item => item.key === entry.key)
      nextEntry = nextModel.entries[Math.min(Math.max(position, 0), nextModel.entries.length - 1)]
    }
    if (nextEntry) selectEntry(nextEntry, nextModel)
    else setSelection({ kind: 'overview' })
  }, [allowDelete, content, model, onChange, selectEntry, selection])

  const saveImage = async () => {
    if (!graphRef.current) return
    setSavingImage(true)
    try {
      await graphRef.current.saveImage()
      notify.success('图谱已保存')
    } catch {
      notify.error('图片导出失败，请重试')
    } finally {
      setSavingImage(false)
    }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && railOpen) setRailOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [railOpen])

  if (!model) {
    return <div className="flex min-h-0 flex-1 items-center justify-center bg-app-surface p-6">
      {isJsonText(content) ? <JsonEditor value={content} readOnly foldable minHeight={0} /> : <Empty description="用例格式无效，请重新生成" />}
    </div>
  }

  const sceneCount = model.modules.reduce((sum, module) => sum + module.scenes.length, 0)
  const railTitle = PAGE_LABEL
  const railCount = sceneCount
  const railSubtitle = `${model.modules.length} 个模块 · ${sceneCount} 个用例类型 · ${model.entries.length} 个用例`
  const activeSceneId = activeScene?.id ?? (selection.kind === 'scene' ? selection.id : undefined)
  const allRailCollapsed = model.modules.length > 0 && model.modules.every(module => collapsedModules.has(module.id))

  const toggleRailModules = () => {
    setCollapsedModules(allRailCollapsed ? new Set() : new Set(model.modules.map(module => module.id)))
  }

  const focus = (() => {
    if (activeEntry) return { label: activeEntry.testCase.displayName, meta: '用例', count: model.entries.length }
    if (selection.kind === 'scene') {
      const scene = model.modules.flatMap(module => module.scenes).find(item => item.id === selection.id)
      return { label: scene?.title ?? '用例类型', meta: '用例类型', count: scene?.cases.length ?? 0 }
    }
    if (selection.kind === 'module') {
      const module = model.modules.find(item => item.id === selection.id)
      return { label: module?.title ?? '模块', meta: '模块', count: module?.entries.length ?? 0 }
    }
    return { label: '全部用例', meta: '模块', count: model.entries.length }
  })()

  return <div className={cx('flex min-h-0 flex-1 flex-col overflow-hidden bg-app-surface', artifactStyles.scope)}>
    <div className="relative flex min-h-0 flex-1 overflow-hidden">
      <aside className={cx(workbenchStyles.rail, 'flex h-full w-[300px] flex-none flex-col border-r border-app-surface-border max-[1360px]:w-[272px] max-[1180px]:w-[300px]', railOpen && workbenchStyles.railOpen)} aria-label="用例索引">
        <div className="flex flex-none flex-col gap-1 px-3 pb-2 pt-3.5">
          <div className={HEADER_GROUP}>
            <h2 className="m-0 text-[12px] font-semibold text-app-surface-text">{railTitle}</h2>
            <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-app-surface-hover px-1.5 font-mono text-[9.5px] text-app-surface-text-muted">{railCount}</span>
            <span className="ml-auto inline-flex items-center gap-0.5">
              {model.modules.length
                ? <button type="button" className="inline-flex size-6 cursor-pointer items-center justify-center rounded-[5px] border-0 bg-transparent text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text" title={allRailCollapsed ? '展开索引列表' : '折叠索引列表'} aria-label={allRailCollapsed ? '展开索引列表' : '折叠索引列表'} onClick={toggleRailModules}>{allRailCollapsed ? <RightOutlined aria-hidden /> : <DownOutlined aria-hidden />}</button>
                : null}
              <button type="button" className="hidden size-6 cursor-pointer items-center justify-center rounded-[5px] border-0 bg-transparent text-[15px] leading-none text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text max-[1180px]:inline-flex" title="关闭用例索引" aria-label="关闭用例索引" onClick={() => setRailOpen(false)}><span aria-hidden>×</span></button>
            </span>
          </div>
          <p className="m-0 text-[11px] leading-[1.45] text-app-surface-text-muted">{railSubtitle}</p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          <div className={RAIL_LIST}>{model.modules.map(module => {
              const collapsed = collapsedModules.has(module.id)
              return <div key={module.id}>
                <button type="button" className={cx('flex w-full cursor-pointer items-center gap-1.5 rounded-[6px] border-0 bg-transparent px-2 py-1.5 text-left text-[11.5px] text-app-surface-text hover:bg-app-surface', selection.kind === 'module' && selection.id === module.id && 'bg-app-accent-selection ring-1 ring-inset ring-app-accent-border')} aria-expanded={!collapsed} onClick={() => {
                  setCollapsedModules(current => {
                    const next = new Set(current)
                    if (next.has(module.id)) next.delete(module.id)
                    else next.add(module.id)
                    return next
                  })
                  setSelection({ kind: 'module', id: module.id })
                }}>
                  {collapsed ? <RightOutlined className={CHEVRON} aria-hidden /> : <DownOutlined className={CHEVRON} aria-hidden />}
                  <span className={`${FLEX_TRUNCATE} font-semibold`}>{module.title}</span>
                  <span className="font-mono text-[9.5px] text-app-surface-text-muted">{module.entries.length}</span>
                </button>
                {collapsed ? null : <div className="ml-2.5 border-l border-app-surface-border pl-1.5">{module.scenes.map(scene => <button key={scene.id} type="button" className={cx('flex w-full cursor-pointer items-center gap-1.5 rounded-[5px] border-0 bg-transparent px-1.5 py-1 text-left text-[11px] text-app-surface-text-muted hover:bg-app-surface hover:text-app-surface-text', activeSceneId === scene.id && 'bg-app-accent-selection text-app-surface-text ring-1 ring-inset ring-app-accent-border')} onClick={() => toggleScene(scene.id)} title={`${scene.title} · ${scene.cases.length} 个用例`}>
                  <i className="size-[5px] flex-none rounded-full bg-[var(--app-graph-edge-reference)]" aria-hidden />
                  <span className={FLEX_TRUNCATE}>{scene.title}</span>
                  <span className="font-mono text-[9.5px]">{scene.cases.length}</span>
                </button>)}</div>}
              </div>
            })}</div>
        </div>

        <footer className="flex flex-none flex-wrap items-center gap-x-2 gap-y-1 border-t border-app-surface-border px-3 py-2 text-[10.5px] text-app-surface-text-muted">
          <span className={INLINE_GAP}><FileTextOutlined aria-hidden />{canEdit ? '草稿可编辑' : '只读产物'}</span>
          <span className="ml-auto font-mono">{model.entries.length} 用例</span>
        </footer>
      </aside>

      {railOpen ? <div className={workbenchStyles.backdrop} aria-hidden onClick={() => setRailOpen(false)} /> : null}

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col" aria-label="完整用例图谱">
        <h1 className="sr-only">{rootTitle}图谱</h1>
        <GeneratedCasesGraph
          ref={graphRef}
          model={model}
          selection={selection}
          expandedSceneIds={expandedScenes}
          rootTitle={rootTitle}
          focusKey={activeEntry?.key}
          focusTick={focusTick}
          canEdit={canEdit}
          canDelete={canDelete}
          onChangeCase={canEdit ? updateCase : undefined}
          onDeleteCase={canDelete ? deleteCase : undefined}
          onSelect={selectFromGraph}
          onSceneSelect={selectSceneFromGraph}
          onModuleSelect={selectModuleFromGraph}
          onCloseDetail={() => setSelection({ kind: 'overview' })}
        />

        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-wrap items-start justify-between gap-2 p-3">
          <button type="button" className="pointer-events-auto inline-flex max-w-[min(520px,calc(100%-8px))] shrink-0 cursor-pointer items-center gap-1.5 rounded-[7px] border border-app-surface-border bg-app-surface px-2.5 py-1.5 text-[11px] text-app-surface-text hover:border-app-accent-border" title="回到总览" onClick={resetSelection}>
            <span className="shrink-0 font-semibold text-app-accent">{focus.meta}</span>
            <span className={FOCUS_LABEL}>{focus.label}</span>
            <span className="shrink-0 rounded-[3px] bg-app-surface-hover px-1 font-mono text-[9.5px] text-app-surface-text-muted">{focus.count}</span>
          </button>
          <div className="pointer-events-auto flex min-w-0 flex-wrap items-center justify-end gap-1.5">
            <button type="button" className="hidden size-7 cursor-pointer items-center justify-center rounded-[6px] border border-app-surface-border bg-app-surface text-app-surface-text-muted hover:bg-app-surface-hover hover:text-app-surface-text max-[1180px]:inline-flex" title="打开用例索引" aria-label="打开用例索引" onClick={() => setRailOpen(true)}><MenuOutlined aria-hidden /></button>
            <button type="button" className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[10.5px] text-app-surface-text hover:border-app-accent-border hover:bg-app-surface-hover" aria-pressed={allExpanded} onClick={toggleAll}>
              {allExpanded ? <MinusSquareOutlined aria-hidden /> : <PlusSquareOutlined aria-hidden />}
              {allExpanded ? '收起全部' : '全部展开'}
            </button>
            <button type="button" className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[10.5px] text-app-surface-text-muted hover:border-app-accent-border hover:bg-app-surface-hover hover:text-app-surface-text" title="适应画布" aria-label="适应画布" onClick={() => graphRef.current?.fitView()}><CompressOutlined aria-hidden />适应画布</button>
            <ProjectActionButton action="write" size="small" icon={<PictureOutlined aria-hidden />} loading={savingImage} onClick={() => void saveImage()}>保存图谱</ProjectActionButton>
          </div>
        </div>

        <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex items-center gap-3 rounded-[6px] border border-app-surface-border bg-app-surface px-2.5 py-1.5 text-[10px] text-app-surface-text-muted" aria-label="图例">
          <span className={INLINE_GAP}><i className="size-1.5 rounded-full bg-[var(--app-graph-edge-primary)]" aria-hidden />模块</span>
          <span className={INLINE_GAP}><i className="size-1.5 rounded-full bg-[var(--app-graph-edge-reference)]" aria-hidden />用例类型</span>
          <span className={INLINE_GAP}><i className="size-[7px] rounded-full border border-app-surface-border" aria-hidden />用例</span>
        </div>
        <span className="pointer-events-none absolute bottom-3 right-3 z-10 text-[10px] text-app-surface-text-muted">滚轮浏览 · Ctrl + 滚轮缩放</span>
      </main>
    </div>
  </div>
}
