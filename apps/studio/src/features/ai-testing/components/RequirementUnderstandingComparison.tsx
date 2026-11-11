import { RequirementArtifactValue, RequirementArtifactScope } from '@/domain/requirements/RequirementArtifactView'
import { pendingRequirementQuestions } from '@/domain/requirements/requirementArtifact'
import { Alert, Collapse, Empty, Input, Tabs } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { readUnderstandingArtifact, type UnderstandingArtifact } from '../utils/understandingComparison'
import { RequirementModuleOverview } from './RequirementModuleOverview'
import { PendingQuestionsLabel } from './PendingQuestionsLabel'
import { RequirementUiInteractionView } from './RequirementUiInteractionView'
import '../styles/understanding-comparison.css'

type Props = { content: unknown; hideTitle?: boolean }
const sections = [{ key: 'summary', label: '需求解析' }, { key: 'ui', label: 'UI 交互' }, { key: 'overview', label: '功能概况' }, { key: 'flows', label: '业务流程' }, { key: 'rules', label: '业务规则' }, { key: 'questions', label: '待确认问题' }]

function UnderstandingContent({ artifact, hideTitle = false }: { artifact: UnderstandingArtifact; hideTitle?: boolean }) {
  const [selectedSection, setSection] = useState('summary')
  const pendingQuestions = pendingRequirementQuestions(artifact.questions)
  const section = selectedSection === 'questions' && !pendingQuestions.length ? 'summary' : selectedSection
  const [moduleId, setModuleId] = useState<string>()
  const [uiTarget, setUiTarget] = useState<{ moduleId: string; operationId: string }>()
  const [search, setSearch] = useState('')
  const rightPane = useRef<HTMLDivElement>(null)
  const module = artifact.modules.find(m => m.id === moduleId)
  useLayoutEffect(() => { if (rightPane.current) rightPane.current.scrollTop = 0 }, [section, module?.id])
  const list = section === 'rules' ? artifact.businessRules : section === 'flows' ? artifact.businessFlows : pendingQuestions
  const filtered = list.filter(item => String(item.name ?? item.question).includes(search))
  function openUiOperation(moduleId: string, operationId: string) {
    setUiTarget({ moduleId, operationId })
    setSection('ui')
    setSearch('')
  }
  function value(content: unknown, field = '') { return <RequirementArtifactValue artifact={artifact} value={content} field={field} /> }
  return <div className="requirement-material-host requirement-understanding-workspace">
    {!hideTitle ? <div className="requirement-material-overview"><strong>{artifact.title}</strong></div> : null}
    <div className="requirement-material-comparison" role="region" aria-label="需求理解结果" tabIndex={0}>
      <section className="requirement-material-panel" data-tab-motion-scope>
        <header className="requirement-material-panel-head"><Tabs className="requirement-understanding-nav" size="small" activeKey={section} onChange={key => { setSection(key); setUiTarget(undefined); setSearch('') }} items={sections.filter(item => item.key !== 'questions' || pendingQuestions.length > 0).map(item => item.key === 'questions' ? { ...item, label: <PendingQuestionsLabel count={pendingQuestions.length} /> } : item)} /></header>
        {['flows', 'rules', 'questions'].includes(section) && <div className="requirement-material-filter"><Input aria-label="搜索需求理解条目" prefix={<SearchOutlined />} placeholder="搜索当前分类" allowClear value={search} onChange={e => setSearch(e.target.value)} /><span className="requirement-material-count">{filtered.length} 条</span></div>}
        <div className="requirement-material-extracted requirement-understanding-content" ref={rightPane} data-tab-motion-panel role="region" aria-label="需求理解内容" tabIndex={0}>
          {section === 'summary' ? artifact.modules.length ? <RequirementModuleOverview artifact={artifact} module={module} onUiOperation={openUiOperation} onModule={id => { setModuleId(current => current === id ? undefined : id) }} onRules={() => { setSearch(''); setSection('rules') }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已识别业务模块" /> : section === 'ui' ? <RequirementUiInteractionView key={uiTarget ? `${uiTarget.moduleId}/${uiTarget.operationId}` : 'default'} initialModuleId={uiTarget?.moduleId} initialOperationId={uiTarget?.operationId} artifact={artifact} onSelectionChange={() => { if (rightPane.current) rightPane.current.scrollTop = 0 }} /> : section === 'overview' ? value(artifact.functionalOverview)
            : filtered.length ? <Collapse key={section} ghost accordion items={filtered.map(item => ({ key: item.id, label: String(item.name ?? item.question), children: value(item) }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配的已记录内容" />}
        </div>

      </section>
    </div>
  </div>
}

export function RequirementUnderstandingComparison({ content, hideTitle }: Props) {
  const result = useMemo(() => {
    if (content == null || (typeof content === 'string' && !content.trim())) return { blank: true as const }
    try { return { artifact: readUnderstandingArtifact(content) } } catch (error) { return { error: error instanceof Error ? error.message : '需求理解内容无法读取' } }
  }, [content])
  if ('blank' in result) return null
  if (!result.artifact) return <Alert type="error" showIcon title={result.error} />
  return <RequirementArtifactScope artifact={result.artifact}><UnderstandingContent hideTitle={hideTitle} artifact={result.artifact} /></RequirementArtifactScope>
}
