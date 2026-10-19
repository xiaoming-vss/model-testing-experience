import { RequirementLazyDetails } from './RequirementLazyDetails'
import { RequirementArtifactValue } from '@/domain/requirements/RequirementArtifactView'
import type { RequirementSourceReference } from '@/domain/requirements/requirementArtifact'
import { toRecord, toRecordArray } from '@/shared/utils/value'
import type { UnderstandingArtifact } from '../utils/understandingComparison'

type Props = {
  control: Record<string, unknown>
  artifact: UnderstandingArtifact
  onSourceReference: (reference: RequirementSourceReference) => void
}

/** Read the recorded facts independently, including each fact's evidence and uncertainty. */
export function RequirementUiControl({ control, artifact, onSourceReference }: Props) {
  const label = toRecord(control.label)?.value
  const options = toRecord(control.options)
  const items = toRecordArray(options?.items)
  function value(content: unknown, field = '') {
    return <RequirementArtifactValue artifact={artifact} value={content} field={field} onSourceReference={onSourceReference} expandCollections compactSources />
  }
  const extra = Object.fromEntries(Object.entries(control).filter(([key]) => !['id', 'label', 'type', 'businessMeaning', 'defaultValue', 'inputRules', 'options'].includes(key)))
  return <RequirementLazyDetails className="requirement-ui-control" summary={<><strong>{label == null ? '未明确控件名称' : String(label)}</strong><span>控件详情</span></>}>
    <div className="requirement-ui-control-body">
      <h4>基本信息</h4>
      <dl className="requirement-ui-facts">
        <div><dt>控件名称</dt><dd>{value(control.label)}</dd></div>
        {control.defaultValue !== undefined && <div><dt>默认值</dt><dd>{value(control.defaultValue)}</dd></div>}
        <div><dt>类型</dt><dd>{value(control.type)}</dd></div>
        <div><dt>选项是否完整</dt><dd>{value(options?.completeness, 'completeness')}</dd></div>
        <div className="requirement-ui-fact-wide"><dt>业务含义</dt><dd>{value(control.businessMeaning)}</dd></div>
      </dl>
      {toRecordArray(control.inputRules).length > 0 && <><h4>输入规则</h4>
        <div className="requirement-ui-input-rules">{value(control.inputRules)}</div></>}
      <h4>实际选项 <span>{items.length} 个已记录条目</span></h4>
      {items.length ? <div className="requirement-ui-options-scroll"><table className="requirement-ui-options" aria-label={`${label ?? '控件'}的实际选项`}>
        <thead><tr><th scope="col">选项值</th><th scope="col">业务含义</th></tr></thead>
        <tbody>{items.map((item, index) => <tr key={String(item.id ?? index)}><td>{value(item.value)}</td><td>{value(item.businessMeaning ?? item.meaning)}{value(Object.fromEntries(Object.entries(item).filter(([key]) => !['id', 'value', 'businessMeaning', 'meaning'].includes(key))))}</td></tr>)}</tbody>
      </table></div> : <p className="requirement-ui-no-options">{options ? '暂无已记录条目' : '未明确'}</p>}
      {Object.keys(extra).length > 0 && <div className="requirement-ui-extra">{value(extra)}</div>}
    </div>
  </RequirementLazyDetails>
}
