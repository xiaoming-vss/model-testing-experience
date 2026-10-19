import { RequirementArtifactValue, RequirementArtifactScope } from '@/domain/requirements/RequirementArtifactView'
import { pendingRequirementQuestions, type RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { Alert, Button, Collapse, Empty, Input, Tabs } from 'antd'
import { SearchOutlined, LinkOutlined } from '@ant-design/icons'
import { createPortal } from 'react-dom'
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'
import { readExtractionArtifact } from '../utils/materialComparison'
import { findUnderstandingEvidence, readUnderstandingArtifact, type UnderstandingArtifact } from '../utils/understandingComparison'
import { RequirementModuleOverview } from './RequirementModuleOverview'
import { RequirementSourcePanel } from './RequirementSourcePanel'
import { RequirementUiInteractionView } from './RequirementUiInteractionView'
import '../styles/understanding-comparison.css'

type Props = { content: unknown; extractionContent: unknown; approved?: boolean; hideTitle?: boolean }
const sections = [{ key: 'summary', label: '需求解析' }, { key: 'ui', label: 'UI 交互' }, { key: 'overview', label: '功能概况' }, { key: 'flows', label: '业务流程' }, { key: 'rules', label: '业务规则' }, { key: 'questions', label: '待确认问题' }]

/** Compact understanding sources omit location/version; keep extraction metadata when both record the same source. */
function mergeSources(extractionSources: UnderstandingArtifact['sources'] | undefined, artifactSources: UnderstandingArtifact['sources']) {
  const merged = new Map<string, UnderstandingArtifact['sources'][number]>()
  for (const source of [...(extractionSources ?? []), ...artifactSources]) {
    const existing = merged.get(source.id)
    merged.set(source.id, existing ? {
      ...existing,
      ...source,
      location: source.location ?? existing.location,
      version: source.version ?? existing.version,
    } : source)
  }
  return [...merged.values()]
}

function UnderstandingContent({ artifact, extractionContent, approved = false, hideTitle = false }: { artifact: UnderstandingArtifact; extractionContent: unknown; approved?: boolean; hideTitle?: boolean }) {
  const extraction = useMemo(() => { try { return readExtractionArtifact(extractionContent) } catch { return undefined } }, [extractionContent])
  const sources = mergeSources(extraction?.sources, artifact.sources)
  const [evidenceOverride, setEvidenceOverride] = useState<boolean>()
  const showEvidence = evidenceOverride ?? !approved
  const [selectedSection, setSection] = useState('summary')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const section = selectedSection === 'questions' && !pendingQuestions.length ? 'summary' : selectedSection
  const [moduleId, setModuleId] = useState<string>()
  const [uiTarget, setUiTarget] = useState<{ moduleId: string; operationId: string }>()
  const [search, setSearch] = useState('')
  const [mode, setMode] = useState<'materials' | 'facts'>('materials')
  const [sourceId, setSourceId] = useState(sources[0]?.id)
  useEffect(() => {
    if (sourceId && sourceId !== 'all' && !sources.some(source => source.id === sourceId)) setSourceId(sources[0]?.id)
  }, [sourceId, sources])
  const [reference, setReference] = useState<RequirementSourceReference>()
  const [locateVersion, requestLocate] = useReducer(v => v + 1, 0)
  const rightPane = useRef<HTMLDivElement>(null)
  const comparisonPane = useRef<HTMLDivElement>(null)
  const [footerSlot, setFooterSlot] = useState<HTMLElement | null>(null)
  useLayoutEffect(() => {
    const footer = comparisonPane.current?.closest('.ant-modal')?.querySelector('.ant-modal-footer')
    const footerItem = document.createElement('span')
    footerItem.className = 'requirement-understanding-footer-count'
    if (footer) { footer.append(footerItem); setFooterSlot(footerItem) }
    return () => { footerItem.remove() }
  }, [])
  const [sourceRevealVersion, revealSource] = useReducer(v => v + 1, 0)
  useLayoutEffect(() => {
    if (!sourceRevealVersion) return
    const pane = comparisonPane.current
    const source = pane?.firstElementChild
    const analysis = pane?.lastElementChild
    // Stacked panes need outer navigation as well as the source's inner locator.
    if (pane && source && analysis && analysis.getBoundingClientRect().top > source.getBoundingClientRect().bottom) pane.scrollTop = 0
  }, [sourceRevealVersion])
  const target = useMemo(() => findUnderstandingEvidence(extraction, reference), [extraction, reference])
  const module = artifact.modules.find(m => m.id === moduleId)
  useLayoutEffect(() => { if (rightPane.current) rightPane.current.scrollTop = 0 }, [section, module?.id])
  const list = section === 'rules' ? artifact.businessRules : section === 'flows' ? artifact.businessFlows : pendingQuestions
  const filtered = list.filter(item => String(item.name ?? item.question).includes(search))
  const locate = useCallback((ref: RequirementSourceReference) => { setEvidenceOverride(true); setReference(ref); setSourceId(ref.sourceId); setMode('materials'); requestLocate(); revealSource() }, [])
  function openUiOperation(moduleId: string, operationId: string) {
    setUiTarget({ moduleId, operationId })
    setSection('ui')
    setSearch('')
    setReference(undefined)
  }
  function value(content: unknown, field = '') { return <RequirementArtifactValue artifact={artifact} value={content} field={field} onSourceReference={locate} /> }

  const sourcePanel = useMemo(() => (<RequirementSourcePanel comparisonLayout artifact={extraction ?? artifact} sources={sources} blocks={extraction?.contentBlocks ?? []} facts={extraction?.extractedFacts ?? []} sourceId={sourceId} onSourceChange={id => { setSourceId(id); requestLocate() }} linkedBlockIds={target.blockIds} linkedFactIds={target.factIds} locateVersion={locateVersion} mode={mode} onModeChange={next => { setMode(next); if (next === 'facts') setSourceId('all'); else setSourceId(reference?.sourceId ?? sources[0]?.id); requestLocate() }} evidence={reference} onSourceReference={locate} emptyMessage={extraction ? undefined : '本次运行没有可用的材料提取记录，仍可核对已登记的来源定位与摘录'} />), [extraction, artifact, sources, sourceId, target, locateVersion, mode, reference, locate])
  return <div className={`requirement-material-host requirement-understanding-workspace${footerSlot ? ' has-footer-summary' : ''}${showEvidence ? '' : ' is-reading-only'}`}>
    {footerSlot && createPortal(<>
      <span>{sources.length} 个材料来源</span>
      <Button type="link" size="small" icon={<LinkOutlined />} aria-pressed={showEvidence} onClick={() => setEvidenceOverride(current => !(current ?? !approved))}>{showEvidence ? '收起材料／依据' : '查看材料／依据'}</Button>
    </>, footerSlot)}
    {(!hideTitle || !footerSlot) && <div className="requirement-material-overview">{!hideTitle && <strong>{artifact.title}</strong>}{!footerSlot && <Button size="small" aria-pressed={showEvidence} onClick={() => setEvidenceOverride(current => !(current ?? !approved))}>{showEvidence ? '收起材料／依据' : '查看材料／依据'}</Button>}</div>}
    <div className="requirement-material-comparison" ref={comparisonPane} role="region" aria-label="材料与需求理解对照" tabIndex={0}>
      {showEvidence && sourcePanel}
      <section className="requirement-material-panel">
        <header className="requirement-material-panel-head"><Tabs className="requirement-understanding-nav" size="small" activeKey={section} onChange={key => { setSection(key); setUiTarget(undefined); setSearch(''); setReference(undefined) }} items={sections.filter(item => item.key !== 'questions' || pendingQuestions.length > 0)} /></header>
        {['flows', 'rules', 'questions'].includes(section) && <div className="requirement-material-filter"><Input aria-label="搜索需求理解条目" prefix={<SearchOutlined />} placeholder="搜索当前分类" allowClear value={search} onChange={e => setSearch(e.target.value)} /><span className="requirement-material-count">{filtered.length} 条</span></div>}
        <div className="requirement-material-extracted requirement-understanding-content" ref={rightPane} role="region" aria-label="需求理解内容" tabIndex={0}>
          {section === 'summary' ? artifact.modules.length ? <RequirementModuleOverview artifact={artifact} module={module} onSourceReference={locate} onUiOperation={openUiOperation} onModule={id => { setModuleId(current => current === id ? undefined : id); setReference(undefined) }} onRules={() => { setSearch(''); setSection('rules') }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已识别业务模块" /> : section === 'ui' ? <RequirementUiInteractionView key={uiTarget ? `${uiTarget.moduleId}/${uiTarget.operationId}` : 'default'} initialModuleId={uiTarget?.moduleId} initialOperationId={uiTarget?.operationId} artifact={artifact} onSourceReference={locate} onSelectionChange={() => { setReference(undefined); if (rightPane.current) rightPane.current.scrollTop = 0 }} /> : section === 'overview' ? value(artifact.functionalOverview)
            : filtered.length ? <Collapse key={section} ghost accordion items={filtered.map(item => ({ key: item.id, label: String(item.name ?? item.question), children: value(item) }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的已记录内容" />}
        </div>
        <footer className="requirement-material-panel-foot"><span>点击说明中的依据，核对左侧材料与来源摘录</span></footer>
      </section>
    </div>
  </div>
}

export function RequirementUnderstandingComparison({ content, extractionContent, approved, hideTitle }: Props) {
  const result = useMemo(() => { try { return { artifact: readUnderstandingArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '需求理解内容无法读取' } } }, [content])
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  return <RequirementArtifactScope artifact={result.artifact}><UnderstandingContent hideTitle={hideTitle} approved={approved} artifact={result.artifact} extractionContent={extractionContent} /></RequirementArtifactScope>
}
