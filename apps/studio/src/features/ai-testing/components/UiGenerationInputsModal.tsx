import { Alert, Button, Modal, Steps } from 'antd'
import { useRef, useState } from 'react'
import { getErrorMessage } from '@/utils/format'
import type { UiGenerationRunInputs, UiGenerationSourceInputs } from '../api/generationChain.api'
import { useUiGenerationSourceSelection } from '../hooks/useUiGenerationSourceSelection'
import { UiGenerationCaseSelector } from './UiGenerationCaseSelector'
import { UiGenerationSourceConfig, type UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'
import '../styles/ui-generation-inputs.css'

export function UiGenerationInputsModal({ requirementId, refreshInputs, source, sourceOptions, onOpenProfile, onClose, onSubmit }: {
  requirementId: string; refreshInputs: boolean; source?: UiGenerationSourceInputs | null; sourceOptions: UiGenerationSourceOptionsState
  onOpenProfile?: () => void; onClose: () => void; onSubmit: (inputs: UiGenerationRunInputs) => Promise<unknown>
}) {
  const [step, setStep] = useState(0)
  const [ids, setIds] = useState<string[] | undefined>(() => source?.cases.length ? source.cases.map(item => item.caseId) : undefined)
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const submitting = useRef(false)
  const { selection, resolved, setProfileVersionId, setRepositoryId, setCommitMode } = useUiGenerationSourceSelection(sourceOptions.data)
  const canContinueSource = Boolean(resolved.ready)
  const canSubmit = Boolean(!saving && ready && ids?.length && resolved.ready)
  const selectedVersion = resolved.version?.label ?? '未选择'
  const selectedRepository = resolved.repository?.pathWithNamespace ?? '未选择'
  async function submit() {
    if (submitting.current || !canSubmit || !ids?.length || !resolved.version || !resolved.repository) return
    submitting.current = true; setSaving(true); setError(undefined)
    try { await onSubmit({ refreshInputs, functionCaseIds: ids, sourceProfileVersionId: resolved.version.versionId, sourceRepositoryId: resolved.repository.repositoryId, sourceCommitMode: selection.commitMode }); onClose() }
    catch (reason) { setError(reason) } finally { setSaving(false); submitting.current = false }
  }
  function next() { if (step === 0 && canContinueSource) setStep(1); else if (step === 1 && canSubmit) setStep(2); else if (step === 2) void submit() }
  return <Modal open centered destroyOnHidden title={refreshInputs ? '更换输入并重新生成' : '选择 UI 生成输入'} width={880} className="gc-ui-input-modal" mask={{ closable: false }} onCancel={() => { if (!saving) onClose() }} footer={null}>
    <Steps className="gc-ui-input-steps" current={step} items={[{ title: '选择来源' }, { title: '选择用例' }, { title: '确认生成' }]} />
    {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
    {step === 0 ? <UiGenerationSourceConfig requirementId={requirementId} optionsState={sourceOptions} selection={selection} resolved={resolved} disabled={saving} caseSummary={<p className="ui-source-note">下一步选择本次生成要使用的正式功能用例。</p>} onProfileVersionChange={setProfileVersionId} onRepositoryChange={setRepositoryId} onCommitModeChange={setCommitMode} onOpenProfile={onOpenProfile} /> : null}
    {step === 1 ? <fieldset disabled={saving} className="gc-ui-input-cases gc-ui-input-step-panel"><UiGenerationCaseSelector requirementId={requirementId} open value={ids} onChange={setIds} onReady={setReady} showIntro={false} tableHeight={460} /></fieldset> : null}
    {step === 2 ? <div className="gc-ui-input-confirm gc-ui-input-step-panel"><Alert showIcon type="warning" title="这次生成会创建新的输入批次" description={refreshInputs ? '当前已通过版本保持不变；新产物审核通过后，才可作为下游正式输入。' : '生成完成后会进入待审核，不会覆盖已有版本。'} /><div className="gc-ui-input-summary"><span>画像版本</span><strong>{selectedVersion}</strong><span>前端仓库</span><strong>{selectedRepository}</strong><span>Commit</span><strong>{selection.commitMode === 'profile' ? resolved.repository?.commit || '未记录' : `分支最新 HEAD · ${resolved.repository?.branch || '未记录'}`}</strong><span>功能用例</span><strong>{ids?.length ?? 0} 条</strong><span>下游影响</span><strong className="is-warning">UI 用例设计、UI 用例 YAML</strong></div><ol className="gc-ui-input-impact"><li><b>冻结输入快照</b><span>仓库、commit、功能用例一次性记录</span></li><li><b>生成元素控件清单</b><span>完成后进入待审核，不覆盖已有版本</span></li><li><b>按需继续下游</b><span>审核通过后可继续生成 UI 设计和 YAML</span></li></ol></div> : null}
    <div className="gc-ui-input-actions"><Button onClick={onClose} disabled={saving}>取消</Button>{step > 0 ? <Button onClick={() => setStep(step - 1)} disabled={saving}>上一步</Button> : null}<Button type="primary" onClick={next} loading={saving} disabled={step === 0 ? !canContinueSource : step === 1 ? !canSubmit : false}>{step === 0 ? '下一步：选择用例' : step === 1 ? '预览变更' : (refreshInputs ? '从元素控件清单重新生成' : '开始生成')}</Button></div>
  </Modal>
}
