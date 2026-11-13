import { Alert, Button, Modal, Steps } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { getErrorMessage } from '@/utils/format'
import type { UiGenerationRunInputs, UiGenerationSourceInputs } from '../api/generationChain.api'
import { useUiGenerationSourceSelection } from '../hooks/useUiGenerationSourceSelection'
import { UiGenerationCaseSelector } from './UiGenerationCaseSelector'
import { UiGenerationSourceConfig, type UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'
import '../styles/ui-generation-inputs.css'

const steps = [{ title: '选择源码' }, { title: '选择用例' }, { title: '核对配置' }]

export function UiGenerationInputsModal({
  requirementId, refreshInputs, source, sourceOptions, busy = false, onOpenProfile, onClose, onSubmit,
}: {
  requirementId: string
  refreshInputs: boolean
  source?: UiGenerationSourceInputs | null
  sourceOptions: UiGenerationSourceOptionsState
  busy?: boolean
  onOpenProfile?: () => void
  onClose: () => void
  onSubmit: (inputs: UiGenerationRunInputs) => Promise<unknown>
}) {
  const [step, setStep] = useState(0)
  const [ids, setIds] = useState<string[] | undefined>(() => source?.cases.length ? source.cases.map(item => item.caseId) : undefined)
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const submitting = useRef(false)
  const stepTop = useRef<HTMLDivElement>(null)
  const { selection, resolved, setProfileVersionId, setRepositoryId, setCommitMode } = useUiGenerationSourceSelection(sourceOptions.data)
  const { version, repository } = resolved
  const canContinueSource = !sourceOptions.loading && !sourceOptions.error && resolved.ready
  const canSubmit = !saving && !busy && ready && Boolean(ids?.length) && canContinueSource

  useEffect(() => { stepTop.current?.closest('.ant-modal-body')?.scrollTo?.(0, 0) }, [step])

  async function submit() {
    if (submitting.current || !canSubmit || !ids?.length || !version || !repository) return
    submitting.current = true
    setSaving(true)
    setError(undefined)
    try {
      await onSubmit({
        refreshInputs,
        functionCaseIds: ids,
        sourceProfileVersionId: version.versionId,
        sourceRepositoryId: repository.repositoryId,
        sourceCommitMode: selection.commitMode,
      })
      onClose()
    } catch (reason) {
      if (getErrorMessage(reason) !== '已取消操作') setError(reason)
    } finally {
      setSaving(false)
      submitting.current = false
    }
  }

  function changeStep(next: number) {
    if (next === 1) setReady(false)
    setError(undefined)
    setStep(next)
  }

  const footer = <div className="gc-ui-input-actions">
    <Button onClick={onClose} disabled={saving}>取消</Button>
    {step > 0 ? <Button onClick={() => changeStep(step - 1)} disabled={saving}>上一步</Button> : null}
    {step === 0 ? <Button type="primary" disabled={!canContinueSource || busy} onClick={() => changeStep(1)}>下一步：选择用例</Button>
      : step === 1 ? <Button type="primary" disabled={!canSubmit} onClick={() => changeStep(2)}>核对配置</Button>
        : <Button type="primary" disabled={!canSubmit} loading={saving} onClick={() => void submit()}>
          {refreshInputs ? '从元素控件清单重新生成' : '开始生成'}
        </Button>}
  </div>

  return <Modal open centered destroyOnHidden title={refreshInputs ? '更换输入并重新生成' : '配置 UI 测试生成'}
    width={880} className="gc-ui-input-modal" mask={{ closable: false }} closable={!saving}
    onCancel={() => { if (!saving) onClose() }} footer={footer}>
    <div ref={stepTop}><Steps className="gc-ui-input-steps" size="small" responsive={false} current={step} items={steps} /></div>
    {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
    {busy && !saving ? <Alert showIcon type="info" title="UI 测试正在运行，请等待本次运行结束。" /> : null}
    {step === 0 ? <UiGenerationSourceConfig requirementId={requirementId} optionsState={sourceOptions}
      selection={selection} resolved={resolved} disabled={saving || busy}
      onProfileVersionChange={setProfileVersionId} onRepositoryChange={setRepositoryId} onCommitModeChange={setCommitMode}
      onOpenProfile={onOpenProfile ? () => { onClose(); onOpenProfile() } : undefined} /> : null}
    {step === 1 ? <fieldset disabled={saving || busy} className="gc-ui-input-cases gc-ui-input-step-panel">
      <UiGenerationCaseSelector requirementId={requirementId} open value={ids} onChange={setIds} onReady={setReady}
        showIntro={false} tableHeight={320} />
    </fieldset> : null}
    {step === 2 ? <div className="gc-ui-input-confirm gc-ui-input-step-panel">
      <dl className="gc-ui-input-summary">
        <dt>画像版本</dt><dd>{version?.label ?? '未选择'}</dd>
        <dt>前端仓库</dt><dd>{repository?.pathWithNamespace ?? '未选择'}</dd>
        <dt>分支</dt><dd>{repository?.branch || '未记录'}</dd>
        <dt>Commit</dt><dd>{selection.commitMode === 'profile' ? repository?.commit || '未记录' : '启动时读取分支最新 HEAD'}</dd>
        <dt>功能用例</dt><dd>{ids?.length ?? 0} 条</dd>
      </dl>
      <Alert showIcon type={refreshInputs ? 'warning' : 'info'} title={refreshInputs
        ? '本次将创建新的输入批次，从元素控件清单重新生成。'
        : '将从元素控件清单开始生成，完成后进入待审核。'} />
    </div> : null}
  </Modal>
}
