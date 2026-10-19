import { RequirementLazyDetails } from './RequirementLazyDetails'
import { RequirementUiControl } from './RequirementUiControl'
import '../styles/understanding-ui-controls.css'
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
const behaviorFields = [['trigger', '触发方式'], ['initialState', '初始状态'], ['dependencies', '条件联动'], ['results', '结果观察'], ['pagination', '分页'], ['sorting', '排序'], ['validationAndFeedback', '校验与反馈']]
const operationFields = [['goal', '操作目的'], ['preconditions', '前置条件'], ['steps', '操作流程'], ['ruleIds', '关联规则'], ['relatedQuestionIds', '关联问题']]
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
    return <RequirementArtifactValue artifact={artifact} value={content} field={field} onSourceReference={onSourceReference} expandCollections compactSources />
  }
  if (!module || !operation) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可查看的操作交互记录" />
  function group(title: string, label: string, fields: string[][], record: Record<string, unknown> | null | undefined) {
    const visibleFields = fields.filter(([field]) => record?.[field] !== undefined
      && !(Array.isArray(record[field]) && record[field].length === 0))
    if (!visibleFields.length) return null
    return <section className="requirement-ui-operation-group" aria-label={label}>
      <RequirementLazyDetails className="requirement-ui-control" key={`${module?.id}/${operation?.id}/${label}`} summary={<><strong>{title}</strong><span>操作详情</span></>}>
        <div className="requirement-ui-control-body">
          <dl className="requirement-ui-facts requirement-ui-operation-facts">{visibleFields.map(([field, name]) => <div key={field} className="requirement-ui-fact-wide"><dt>{name}</dt><dd>{value(record?.[field] ?? null, field)}</dd></div>)}</dl>
        </div>
      </RequirementLazyDetails>
    </section>
  }
  return <div className="requirement-ui-interaction">
    <div className="requirement-ui-selectors">
      <label><span>选择操作</span><Select
        aria-label="选择操作"
        showSearch
        optionFilterProp="searchText"
        value={JSON.stringify([module.id, operation.id])}
        labelRender={() => `${module.name} / ${operation.name}`}
        options={modules.map(owner => ({ label: owner.name, options: owner.operations.map(item => ({
          value: JSON.stringify([owner.id, item.id]), label: item.name, searchText: `${owner.name} ${item.name}`,
        })) }))}
        onChange={key => {
          const [ownerId, nextOperationId] = JSON.parse(key) as [string, string]
          setModuleId(ownerId); setOperationId(nextOperationId); onSelectionChange()
        }}
      /></label>
    </div>
    <section className="requirement-ui-section" aria-label="UI 控件详情">
      <h3>控件与字段 <span>{controls.length} 个控件记录</span></h3>
      {controls.length ? <div key={`${module.id}/${operation.id}`} className="requirement-ui-controls">{controls.map((control, index) => <RequirementUiControl key={String(control.id ?? index)} control={control} artifact={artifact} onSourceReference={onSourceReference} />)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无控件记录" />}
    </section>
    {group('触发与反馈', 'UI 行为详情', behaviorFields, interaction)}
    {group('操作步骤与关联规则', 'UI 操作步骤', operationFields, operation)}
  </div>
}
