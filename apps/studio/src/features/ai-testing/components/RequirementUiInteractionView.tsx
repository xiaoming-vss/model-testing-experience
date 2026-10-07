import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import type { RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import { Empty, Select } from 'antd'
import { useState } from 'react'
import type { UnderstandingArtifact } from '../utils/understandingComparison'

type Props = {
  artifact: UnderstandingArtifact
  onSourceReference: (reference: RequirementSourceReference) => void
  onSelectionChange: () => void
  initialModuleId?: string
  initialOperationId?: string
}
const behaviorFields = ['trigger', 'initialState', 'dependencies', 'results', 'pagination', 'sorting', 'validationAndFeedback']
function controlCount(operation: Record<string, unknown>) {
  return toRecordArray(toRecord(operation.interaction)?.controls).length
}

/** A direct view of recorded interaction fields; it never infers UI from operation names. */
export function RequirementUiInteractionView({ artifact, onSourceReference, onSelectionChange, initialModuleId, initialOperationId }: Props) {
  const modules = artifact.modules.filter(module => module.operations.length > 0)
  const [moduleId, setModuleId] = useState(() => initialModuleId ?? (modules.find(module => module.operations.some(controlCount)) ?? modules[0])?.id)
  const [operationId, setOperationId] = useState(initialOperationId)
  const module = modules.find(module => module.id === moduleId) ?? modules[0]
  const operation = module?.operations.find(operation => operation.id === operationId)
    ?? module?.operations.find(operation => controlCount(operation) > 0) ?? module?.operations[0]
  const interaction = toRecord(operation?.interaction)
  const controls = toRecordArray(interaction?.controls)
  function value(content: unknown, field = '') {
    return <RequirementArtifactValue artifact={artifact} value={content} field={field} onSourceReference={onSourceReference} expandCollections />
  }
  if (!module || !operation) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可查看的操作交互记录" />
  const behavior = Object.fromEntries(behaviorFields.map(field => [field, interaction?.[field] ?? null]))
  return <div className="requirement-ui-interaction">
    <div className="requirement-ui-selectors">
      <label><span>所属模块</span><Select aria-label="UI 所属模块" value={module.id} options={modules.map(module => ({ value: module.id, label: module.name }))} onChange={id => { setModuleId(id); setOperationId(undefined); onSelectionChange() }} /></label>
      <label><span>所属操作</span><Select aria-label="UI 所属操作" value={operation.id} options={module.operations.map(operation => ({ value: operation.id, label: operation.name }))} onChange={id => { setOperationId(id); onSelectionChange() }} /></label>
    </div>
    <section className="requirement-ui-section" aria-label="UI 控件详情">
      <h3>控件与字段 <span>{controls.length} 个控件记录</span></h3>
      {controls.length ? value(controls, 'controls') : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无控件记录" />}
    </section>
    <section className="requirement-ui-section" aria-label="UI 行为详情"><h3>触发与反馈</h3>{value(behavior)}</section>
    <section className="requirement-ui-section" aria-label="UI 操作步骤"><h3>操作步骤与关联规则</h3>{value(Object.fromEntries(['goal', 'preconditions', 'steps', 'ruleIds', 'relatedQuestionIds'].map(field => [field, operation[field] ?? null])))}</section>
  </div>
}
