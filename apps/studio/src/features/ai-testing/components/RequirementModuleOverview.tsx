import { FileTextOutlined, OrderedListOutlined, AppstoreOutlined, RightOutlined, VideoCameraOutlined, BuildOutlined, SettingOutlined, FolderOpenOutlined, LinkOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { Button, Empty, Tag, Tooltip, Popover } from 'antd'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import { pendingRequirementQuestions, type RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { RequirementModuleOperations } from './RequirementModuleOperations'
import type { UnderstandingArtifact, UnderstandingModule } from '../utils/understandingComparison'

type Props = {
  artifact: UnderstandingArtifact
  module?: UnderstandingModule
  onSourceReference: (ref: RequirementSourceReference) => void
  onModule: (moduleId: string) => void
  onRules: () => void
  onUiOperation: (moduleId: string, operationId: string) => void
}
const statuses: Record<string, string> = { unconfirmed: '待确认', conflicting: '存在冲突', example: '示例', not_applicable: '不适用' }
function text(value: unknown): string {
  const fact = toRecord(value)
  const raw = fact ? fact.value : value
  return raw == null ? (fact?.confirmationStatus === 'not_applicable' ? '不适用' : '未明确') : Array.isArray(raw) ? raw.map(String).join('、') : String(raw)
}
function refs(value: unknown): RequirementSourceReference[] {
  return toRecordArray(toRecord(value)?.sourceReferences).flatMap(ref => typeof ref.sourceId === 'string' && typeof ref.locator === 'string'
    ? [{ sourceId: ref.sourceId, locator: ref.locator, excerpt: typeof ref.excerpt === 'string' ? ref.excerpt : null }] : [])
}

export function RequirementModuleOverview({ artifact, module, onSourceReference, onModule, onRules, onUiOperation }: Props) {
  const [detailOpen, setDetailOpen] = useState<'purpose' | 'flow'>()
  const operationIds = new Set((module?.operations ?? []).map(operation => operation.id))
  const ruleIds = new Set((module?.operations ?? []).flatMap(operation => Array.isArray(operation.ruleIds) ? operation.ruleIds : []))
  const rules = artifact.businessRules.filter(rule => !module || ruleIds.has(rule.id)
    || (Array.isArray(rule.moduleIds) && rule.moduleIds.includes(module.id))
    || (Array.isArray(rule.operationIds) && rule.operationIds.some(id => operationIds.has(String(id)))))
  const questions = pendingRequirementQuestions(artifact.questions)
  const purpose = toRecord(module?.purpose)
  const purposeQuestions = questions.filter(question => Array.isArray(purpose?.relatedQuestionIds) && purpose.relatedQuestionIds.includes(question.id))
  function evidence(value: unknown) {
    return refs(value).map((ref, index) => {
      const source = artifact.sources.find(item => item.id === ref.sourceId)
      const label = `${source?.name ?? ref.sourceId} · ${ref.locator}`
      return <Tooltip key={`${ref.sourceId}/${ref.locator}/${index}`} title={ref.excerpt ? `${label}：${ref.excerpt}` : label}>
        <button className="requirement-reading-citation" aria-label={label} onClick={() => { setDetailOpen(undefined); onSourceReference(ref) }}>来源：{ref.locator.split(/[（(]/)[0]}</button>
      </Tooltip>
    })
  }
  return <div className="requirement-module-overview">
    <section className="requirement-reading-section">
      <h3 aria-label="业务模块"><AppstoreOutlined aria-hidden />业务模块{module && <Popover trigger="click" open={detailOpen === 'flow'} onOpenChange={open => setDetailOpen(open ? 'flow' : undefined)} title="当前模块入口与使用说明" content={<div className="requirement-reading-flow-popover"><RequirementArtifactValue artifact={artifact} value={{ entryPoints: module.entryPoints, userVisibleFlow: module.userVisibleFlow, relatedQuestionIds: module.relatedQuestionIds }} onSourceReference={ref => { setDetailOpen(undefined); onSourceReference(ref) }} expandCollections /></div>}><Button type="text" size="small" aria-label="查看当前模块入口与使用说明" icon={<LinkOutlined />} /></Popover>}</h3>
      <ul className="requirement-module-navigation" aria-label="业务模块导航">{artifact.modules.map(candidate => {
        const purpose = toRecord(candidate.purpose)
        return <li key={candidate.id}>
          <button className="requirement-module-card" aria-pressed={candidate.id === module?.id} onClick={() => { setDetailOpen(undefined); onModule(candidate.id) }} aria-label={candidate.name}>
            <span className="requirement-reading-step-icon" aria-hidden>{/上传|采集/.test(candidate.name) ? <VideoCameraOutlined /> : /语义/.test(candidate.name) ? <FileTextOutlined /> : /切片|清洗/.test(candidate.name) ? <BuildOutlined /> : /模型|审核/.test(candidate.name) ? <SettingOutlined /> : /打包|导出/.test(candidate.name) ? <FolderOpenOutlined /> : <AppstoreOutlined />}</span>
            <strong>{candidate.name}</strong>
            <span className="requirement-reading-step-note">{text(candidate.purpose)}</span>
            {purpose && statuses[String(purpose.confirmationStatus)] && <span className="requirement-reading-step-status">{statuses[String(purpose.confirmationStatus)]}</span>}
          </button>
        </li>
      })}</ul>
    </section>
    {module && <section className="requirement-reading-section">
      <h3 aria-label="模块说明"><FileTextOutlined aria-hidden />模块说明{refs(module.purpose).length > 0 && <Popover trigger="click" open={detailOpen === 'purpose'} onOpenChange={open => setDetailOpen(open ? 'purpose' : undefined)} title="模块说明依据" content={<div className="requirement-reading-source-popover">{evidence(module.purpose)}</div>}><Button type="text" size="small" aria-label="查看模块说明依据" icon={<LinkOutlined />} /></Popover>}</h3>
      <p className="requirement-reading-purpose">{text(module.purpose)}</p>
      <div className="requirement-reading-meta">
        {purpose && statuses[String(purpose.confirmationStatus)] && <Tag color={purpose.confirmationStatus === 'conflicting' ? 'error' : purpose.confirmationStatus === 'unconfirmed' ? 'warning' : 'default'}>{statuses[String(purpose.confirmationStatus)]}</Tag>}
        {!!purposeQuestions.length && <details className="requirement-reading-questions"><summary>{purposeQuestions.length} 个待确认问题</summary><ul>{purposeQuestions.map(question => <li key={question.id}>{question.question}</li>)}</ul></details>}
      </div>
    </section>}
    <section className="requirement-reading-section">
      <h3 aria-label="关联业务规则"><OrderedListOutlined aria-hidden />关联业务规则{rules.length > 4 && <Button type="link" size="small" onClick={onRules}>全部规则 <RightOutlined /></Button>}</h3>
      {rules.length ? <ol className="requirement-reading-rules">{rules.slice(0, 4).map((rule, index) => {
        const expected = toRecordArray(rule.expectedBehavior)
        const citation = expected[0] ?? rule.trigger
        return <li key={rule.id}><span className="requirement-reading-rule-index">{index + 1}</span><details>
          <summary title={rule.name}>{expected.length ? text(expected[0]) : rule.name}</summary>
          <RequirementArtifactValue artifact={artifact} value={rule} onSourceReference={onSourceReference} />
        </details><div className="requirement-reading-rule-source">{evidence(citation).slice(0, 1)}</div></li>
      })}</ol> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此模块暂无明确关联的业务规则" />}
    </section>
    <RequirementModuleOperations artifact={artifact} moduleId={module?.id} onSourceReference={onSourceReference} onUiOperation={onUiOperation} />
  </div>
}
