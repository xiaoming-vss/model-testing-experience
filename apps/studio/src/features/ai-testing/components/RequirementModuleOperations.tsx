import { RequirementLazyDetails } from './RequirementLazyDetails'
import { AppstoreOutlined } from '@ant-design/icons'
import { Button, Collapse, Empty } from 'antd'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import type { RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import type { UnderstandingArtifact } from '../utils/understandingComparison'

type Props = {
  artifact: UnderstandingArtifact
  moduleId?: string
  operationId?: string
  onSourceReference: (ref: RequirementSourceReference) => void
  onUiOperation: (moduleId: string, operationId: string) => void
}

export function RequirementModuleOperations({ artifact, moduleId, operationId, onSourceReference, onUiOperation }: Props) {
  return <section className="requirement-reading-section requirement-reading-operations" aria-label="模块操作详情">
    <h3><AppstoreOutlined aria-hidden />模块与操作</h3>
    <div key={`${moduleId}/${operationId ?? ''}`}>
      {artifact.modules.filter(module => !moduleId || module.id === moduleId).map(module => <RequirementLazyDetails key={module.id} className="requirement-operation-module" defaultOpen={module.id === moduleId} summary={module.name}>
        {module.operations.length ? <Collapse ghost accordion defaultActiveKey={module.id === moduleId ? operationId ?? module.operations[0].id : module.operations[0].id} items={module.operations.map(operation => ({
          key: operation.id,
          label: operation.name,
          children: <>
            <div className="requirement-operation-actions"><Button type="link" size="small" aria-label={`查看 UI 交互：${module.name} / ${operation.name}`} onClick={() => onUiOperation(module.id, operation.id)}>查看 UI 交互</Button></div>
            <RequirementArtifactValue artifact={artifact} value={Object.fromEntries(Object.entries(operation).filter(([field]) => field !== 'interaction'))} onSourceReference={onSourceReference} />
          </>,
        }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此模块暂无已记录操作" />}
      </RequirementLazyDetails>)}
    </div>
  </section>
}
