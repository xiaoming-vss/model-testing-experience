import '../styles/ui-generation.css'
import { Alert, Button, Input, Modal, Tag } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { api } from '@/services/api'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { getErrorMessage } from '@/utils/format'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { LlmConnectionSelectModal } from './LlmConnectionSelectModal'
import { ArtifactModeSwitch } from './ArtifactViewTabs'
import { UiStageVisual } from './uiStageVisual/UiStageVisual'
import { UiSemanticReview } from './UiSemanticReview'
import { RevisionDivider, RevisionSidePanel } from './RevisionSidePanel'
import { renderApiCaseGenerateTaskRunStatusTag } from '../utils/taskStatus'
import {
  currentUiGenerationStage,
  uiStageArtifactText,
  uiStageEditable,
  uiStageHasContent,
  uiStageMeta,
} from '../utils/uiGenerationStage'
import type { UiGenerationStage } from '../utils/uiGenerationStage'
import type { UiCaseGenerateTaskRun } from '../types'

type StageAction = 'save' | 'approve' | 'reject' | 'revise' | 'retry'

/**
 * 三阶段 UI 运行的单个阶段审核弹窗。布局与功能测试阶段审核一致：正文只有阶段产物，
 * 审核备注和阶段动作固定在弹窗底部，继续优化使用右侧优化面板。
 */
export function UiGenerationStageReviewModal({ open, run, projectId, stage, extraFooter = [], onClose, onUpdated, onDirtyChange }: {
  open: boolean
  run: UiCaseGenerateTaskRun
  projectId?: string
  /** 要展示的阶段；缺省跟随当前阶段。阶段还没有内容时也回落到当前阶段。 */
  stage?: UiGenerationStage
  /** 审核通过后的导入、查看正式套件等入口。 */
  extraFooter?: ReactNode[]
  onClose: () => void
  onUpdated: (run: UiCaseGenerateTaskRun) => void
  onDirtyChange: (dirty: boolean) => void
}) {
  const { can } = useProjectAccess(projectId ?? '')
  const current = currentUiGenerationStage(run)
  const shown = stage && uiStageHasContent(run, stage) ? stage : current
  const info = uiStageMeta(shown)
  const saved = uiStageArtifactText(run, shown)
  const [draft, setDraft] = useState(saved)
  const [comment, setComment] = useState('')
  const [revision, setRevision] = useState('')
  const [revisionOpen, setRevisionOpen] = useState(false)
  const [revisionFooter, setRevisionFooter] = useState<HTMLDivElement | null>(null)
  const [modelAction, setModelAction] = useState<'approve' | 'retry' | null>(null)
  const [parseError, setParseError] = useState('')
  const [viewMode, setViewMode] = useState<'visual' | 'raw'>('visual')
  useEffect(() => { setDraft(saved) }, [saved, shown, run.runId])
  useEffect(() => {
    setComment('')
    setRevision('')
    setRevisionOpen(false)
    setModelAction(null)
    setParseError('')
    setViewMode('visual')
  }, [shown, run.runId])
  const dirty = draft !== saved
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false) }, [dirty, onDirtyChange])
  const editable = uiStageEditable(run, shown)
  const failed = shown === current && ['failed', 'error'].includes(run.status ?? '') && run.reviewStatus === 'pending'
  function outputBody(): Record<string, unknown> {
    return info.field
      ? { stage: shown, configJson: { [info.field]: JSON.parse(draft) } }
      : { stage: shown, resultYaml: draft }
  }
  const mutation = useMutation({
    mutationFn: async ({ action, connectionId }: { action: StageAction; connectionId?: string }) => {
      const body = { stage: shown, reviewComment: comment, ...(connectionId ? { llmConnectionId: connectionId } : {}) }
      if (action === 'save') return api.saveUiGenerationStage(run.runId!, outputBody())
      if (action === 'revise') return api.reviseUiGenerationStage(run.runId!, { ...body, ...outputBody(), revisionInstruction: revision })
      if (action === 'retry') return api.retryUiGenerationStage(run.runId!, body)
      return api.reviewUiGenerationStage(run.runId!, { ...body, action })
    },
    onSuccess: updated => {
      onUpdated(updated)
      setModelAction(null)
      setComment('')
      setRevision('')
      setRevisionOpen(false)
      setParseError('')
    },
  })
  function submit(action: StageAction, connectionId?: string) {
    try {
      if (action === 'save' || action === 'revise') outputBody()
      setParseError('')
      mutation.mutate({ action, connectionId })
    } catch (error) { setParseError(getErrorMessage(error)) }
  }
  const copyLabel = info.language === 'json' ? '复制 JSON' : '复制 YAML'
  const rawLabel = info.language === 'json' ? 'JSON' : 'YAML'
  const title = editable ? '审核' : info.label
  const footer = revisionOpen ? <div ref={setRevisionFooter} /> : [
    ...(editable ? [
      <div key="comment" className="ai-task-stage-review-footer-comment">
        <Input.TextArea
          className="ai-task-stage-review-comment"
          aria-label="审核备注"
          placeholder="审核备注，可选"
          rows={2}
          value={comment}
          onChange={event => setComment(event.target.value)}
        />
      </div>,
    ] : []),
    <Button key="close" onClick={onClose}>关闭</Button>,
    ...(editable ? [
      <ProjectActionButton action="write" operation="save" key="save" disabled={!dirty || mutation.isPending} onClick={() => submit('save')}>
        保存
      </ProjectActionButton>,
      <ProjectActionButton action="execute" key="revise" disabled={mutation.isPending} onClick={() => setRevisionOpen(true)}>
        继续优化
      </ProjectActionButton>,
      <ProjectActionButton action="review" key="reject" danger ghost disabled={dirty || mutation.isPending} onClick={() => submit('reject')}>
        审核不通过
      </ProjectActionButton>,
      <ProjectActionButton action="review" key="approve" type="primary" disabled={dirty || !saved || mutation.isPending}
        onClick={() => shown === 'ui_yaml' ? submit('approve') : setModelAction('approve')}>
        {shown === 'ui_yaml' ? '批准 YAML' : '审核通过并继续'}
      </ProjectActionButton>,
    ] : []),
    ...(!editable && failed ? [
      <ProjectActionButton action="execute" key="retry" loading={mutation.isPending} onClick={() => setModelAction('retry')}>
        重试本阶段
      </ProjectActionButton>,
    ] : []),
    ...extraFooter,
  ]
  return <>
    <Modal
      mask={{ closable: false }}
      className={`ai-task-run-result-modal functional-artifact-modal review functional-stage-review-modal${editable && !revisionOpen ? ' stage-review-with-comment' : ''}`}
      title={title}
      open={open}
      onCancel={onClose}
      footer={footer}
      width="min(2000px, calc(100vw - 56px))"
      centered
      destroyOnHidden
    >
      <div className={`revision-workspace${revisionOpen ? ' is-revising' : ''}`}><div className="revision-source">
        <div className="ai-task-run-result-modal-content review">
          <div className="ai-task-stage-review-popover ui-generation-stage-panel">
            <div className="ai-task-run-result-popover-header">
              <span>阶段产物 {info.label}</span>
              <div className="ai-task-stage-review-mini-tags">
                {renderApiCaseGenerateTaskRunStatusTag(run.status)}
                {editable ? <Tag color="processing">{viewMode === 'visual' ? '待审核/可视化' : '待审核/可编辑'}</Tag> : null}
              </div>
            </div>
            <ArtifactModeSwitch
              value={viewMode}
              onChange={value => setViewMode(value as 'visual' | 'raw')}
              options={[{ label: '可视化', value: 'visual' }, { label: rawLabel, value: 'raw' }]}
              copyText={draft}
              copyLabel={copyLabel}
            />
            {editable ? <div className="ai-task-stage-review-note compact">
              <strong>{viewMode === 'visual' ? '待审核/可视化预览' : '待审核/可编辑'}</strong>
              <span>{viewMode === 'visual'
                ? '可视化视图用于核对结构；需要修改时切换到 JSON/YAML，保存或审核仍在底部操作。'
                : '当前编辑的是本阶段产物，保存后会写回当前阶段输出，审核通过后继续进入下一阶段。'}</span>
            </div> : null}
            {shown === 'ui_yaml' ? <UiSemanticReview summary={run.resultSummaryJson} dirty={dirty}
              onRevise={editable && can('execute') && !mutation.isPending ? instruction => {
                setRevision(instruction)
                setRevisionOpen(true)
              } : undefined} /> : null}
            {viewMode === 'visual' ? <div className="ui-generation-stage-visual">
              <UiStageVisual stage={shown} content={draft} onShowRaw={() => setViewMode('raw')} />
            </div> : <div className="ui-generation-stage-editor">
              <TextCodeEditor value={draft} onChange={setDraft} readOnly={!editable || !can('write') || mutation.isPending}
                language={info.language} ariaLabel={`${info.label} ${info.language === 'json' ? 'JSON' : 'YAML'}`}
                foldable height="100%" minHeight={0} />
            </div>}
            {!saved && !editable ? <Alert type="info" title={shown === current ? '当前阶段尚未生成产物' : '此阶段尚未生成'} /> : null}
            {parseError || mutation.error ? <Alert type="error" showIcon title={parseError || getErrorMessage(mutation.error)} /> : null}
            {run.errorMessage ? <Alert type="error" showIcon title={run.errorMessage} /> : null}
            {run.status === 'canceled' && run.reviewComment ? <Alert type="warning" showIcon title="本阶段已拒绝" description={run.reviewComment} /> : null}
          </div>
        </div>
      </div>{revisionOpen ? <>
        <RevisionDivider />
        <RevisionSidePanel
          footerContainer={revisionFooter}
          projectId={projectId}
          value={revision}
          onChange={setRevision}
          loading={mutation.isPending}
          onCancel={() => { setRevisionOpen(false); setRevision('') }}
          onSubmit={connectionId => submit('revise', connectionId)}
        />
      </> : null}</div>
    </Modal>
    <LlmConnectionSelectModal open={Boolean(modelAction)} projectId={projectId} loading={mutation.isPending}
      onClose={() => setModelAction(null)} onConfirm={connectionId => modelAction && submit(modelAction, connectionId)} />
  </>
}
