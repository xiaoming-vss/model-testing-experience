import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { pendingRequirementQuestions, type RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { Alert, Button, Collapse, Empty, Input, Select, Tabs } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'
import { readExtractionArtifact } from '../utils/materialComparison'
import { findUnderstandingEvidence, readUnderstandingArtifact, type UnderstandingArtifact } from '../utils/understandingComparison'
import { RequirementSourcePanel } from './RequirementSourcePanel'
import { RequirementUiInteractionView } from './RequirementUiInteractionView'
import '../styles/understanding-comparison.css'

type Props = { content: unknown; extractionContent: unknown }
const sections = [{ key: 'modules', label: '模块与操作' }, { key: 'ui', label: 'UI 交互' }, { key: 'overview', label: '功能概况' }, { key: 'flows', label: '业务流程' }, { key: 'rules', label: '业务规则' }, { key: 'questions', label: '待确认问题' }]

function UnderstandingContent({ artifact, extractionContent }: { artifact: UnderstandingArtifact; extractionContent: unknown }) {
  const extraction = useMemo(() => { try { return readExtractionArtifact(extractionContent) } catch { return undefined } }, [extractionContent])
  const sources = useMemo(() => [...new Map([...(extraction?.sources ?? []), ...artifact.sources].map(s => [s.id, s])).values()], [artifact.sources, extraction?.sources])
  const [selectedSection, setSection] = useState('modules')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const section = selectedSection === 'questions' && !pendingQuestions.length ? 'modules' : selectedSection
  const [moduleId, setModuleId] = useState(artifact.modules[0]?.id)
  const [uiTarget, setUiTarget] = useState<{ moduleId: string; operationId: string }>()
  const [search, setSearch] = useState('')
  const [mode, setMode] = useState<'materials' | 'facts'>('materials')
  const [sourceId, setSourceId] = useState(sources[0]?.id)
  const [reference, setReference] = useState<RequirementSourceReference>()
  const [locateVersion, requestLocate] = useReducer(v => v + 1, 0)
  const rightPane = useRef<HTMLDivElement>(null)
  const target = useMemo(() => findUnderstandingEvidence(extraction, reference), [extraction, reference])
  const module = artifact.modules.find(m => m.id === moduleId) ?? artifact.modules[0]
  useLayoutEffect(() => { if (rightPane.current) rightPane.current.scrollTop = 0 }, [section, module?.id])
  const list = section === 'rules' ? artifact.businessRules : section === 'flows' ? artifact.businessFlows : pendingQuestions
  const filtered = list.filter(item => String(item.name ?? item.question).includes(search))
  function locate(ref: RequirementSourceReference) { setReference(ref); setSourceId(ref.sourceId); setMode('materials'); requestLocate() }
  function openUiOperation(moduleId: string, operationId: string) {
    setUiTarget({ moduleId, operationId })
    setSection('ui')
    setSearch('')
    setReference(undefined)
  }
  function value(content: unknown, field = '') { return <RequirementArtifactValue artifact={artifact} value={content} field={field} onSourceReference={locate} /> }
  const moduleSummary = module && Object.fromEntries(Object.entries(module).filter(([key]) => !['id', 'name', 'operations'].includes(key)))
  return <div className="requirement-material-host">
    <div className="requirement-material-overview"><strong>{artifact.title}</strong><span>{artifact.modules.length} 个模块 · {artifact.businessFlows.length} 条流程 · {artifact.businessRules.length} 条规则 · {pendingQuestions.length} 个待确认问题</span></div>
    <div className="requirement-material-comparison" role="region" aria-label="材料与需求理解对照" tabIndex={0}>
      <RequirementSourcePanel artifact={extraction ?? artifact} sources={sources} blocks={extraction?.contentBlocks ?? []} facts={extraction?.extractedFacts ?? []} sourceId={sourceId} onSourceChange={id => { setSourceId(id); requestLocate() }} linkedBlockIds={target.blockIds} linkedFactIds={target.factIds} locateVersion={locateVersion} mode={mode} onModeChange={next => { setMode(next); if (next === 'facts') setSourceId('all'); else setSourceId(reference?.sourceId ?? sources[0]?.id); requestLocate() }} evidence={reference} onSourceReference={locate} emptyMessage={extraction ? undefined : '本次运行没有可用的材料提取记录，仍可核对已登记的来源定位与摘录'} />
      <section className="requirement-material-panel">
        <header className="requirement-material-panel-head"><Tabs className="requirement-understanding-nav" size="small" activeKey={section} onChange={key => { setSection(key); setUiTarget(undefined); setSearch(''); setReference(undefined) }} items={sections.filter(item => item.key !== 'questions' || pendingQuestions.length > 0)} /></header>
        {section === 'modules' && <div className="requirement-material-filter"><Select className="requirement-understanding-module-picker" aria-label="业务模块" value={module?.id} disabled={!artifact.modules.length} onChange={id => { setModuleId(id); setReference(undefined) }} options={artifact.modules.map(m => ({ value: m.id, label: m.name }))} /><span className="requirement-material-count">{module?.operations.length ?? 0} 个操作</span></div>}
        {['flows', 'rules', 'questions'].includes(section) && <div className="requirement-material-filter"><Input aria-label="搜索需求理解条目" prefix={<SearchOutlined />} placeholder="搜索当前分类" allowClear value={search} onChange={e => setSearch(e.target.value)} /><span className="requirement-material-count">{filtered.length} 条</span></div>}
        <div className="requirement-material-extracted requirement-understanding-content" ref={rightPane} role="region" aria-label="需求理解内容" tabIndex={0}>
          {section === 'ui' ? <RequirementUiInteractionView key={uiTarget ? `${uiTarget.moduleId}/${uiTarget.operationId}` : 'default'} initialModuleId={uiTarget?.moduleId} initialOperationId={uiTarget?.operationId} artifact={artifact} onSourceReference={locate} onSelectionChange={() => { setReference(undefined); if (rightPane.current) rightPane.current.scrollTop = 0 }} /> : section === 'overview' ? value(artifact.functionalOverview) : section === 'modules' ? module ? <>
            <h3>{module.name}</h3>
            <Collapse ghost items={[{ key: 'module-summary', label: '模块说明、入口与使用流程', children: value(moduleSummary) }]} />
            {module.operations.length ? <Collapse key={module.id} ghost accordion defaultActiveKey={module.operations[0].id} items={module.operations.map(operation => ({ key: operation.id, label: operation.name, children: <>
              <div className="requirement-operation-actions"><Button type="link" size="small" aria-label={`查看 UI 交互：${module.name} / ${operation.name}`} onClick={() => openUiOperation(module.id, operation.id)}>查看 UI 交互</Button></div>
              {value(Object.fromEntries(Object.entries(operation).filter(([field]) => field !== 'interaction')))}
            </> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此模块暂无已记录操作" />}
          </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已识别业务模块" />
            : filtered.length ? <Collapse key={section} ghost accordion items={filtered.map(item => ({ key: item.id, label: String(item.name ?? item.question), children: value(item) }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的已记录内容" />}
        </div>
        <footer className="requirement-material-panel-foot"><span>点击说明中的依据，核对左侧材料与来源摘录</span></footer>
      </section>
    </div>
  </div>
}

export function RequirementUnderstandingComparison({ content, extractionContent }: Props) {
  const result = useMemo(() => { try { return { artifact: readUnderstandingArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '需求理解内容无法读取' } } }, [content])
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  return <UnderstandingContent artifact={result.artifact} extractionContent={extractionContent} />
}
