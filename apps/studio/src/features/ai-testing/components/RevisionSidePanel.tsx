import { Alert, Button, Input, Select, Spin } from 'antd'
import { PictureOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, listItems } from '@/services/api'
import { downloadStoredFile, uploadStoredFile } from '@/shared/api/files'
import { ActionButton } from '@/shared/components/ActionButton'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import type { RevisionAttachment } from '../hooks/useRevisionAttachments'
import { parseQuestionRevisionDraft, revisionInstructionText, updateQuestionRevisionDraft } from '../utils/functionalRevision'
import './RevisionSidePanel.css'

const MAX_ATTACHMENTS = 6
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const IMAGE_TYPES = ['image/png', 'image/jpeg']

type Props = {
  footerContainer?: HTMLElement | null
  projectId?: string
  value: string
  sourceEditable?: boolean
  onChange: (value: string) => void
  /** 不支持图片附件的修订流程省略这三个属性，侧栏只保留指令和模型选择。 */
  attachments?: RevisionAttachment[]
  onAddAttachment?: (attachment: RevisionAttachment) => void
  onRemoveAttachment?: (fileId: string) => void
  onSubmit: (connectionId: string) => void
  onCancel: () => void
  loading: boolean
}

export function RevisionSidePanel({ footerContainer, projectId, value, sourceEditable = true, onChange, attachments, onAddAttachment, onRemoveAttachment, onSubmit, onCancel, loading }: Props) {
  const [selectedId, setSelectedId] = useState<string>()
  const [uploading, setUploading] = useState(0)
  const [questionIndex, setQuestionIndex] = useState(0)
  const draft = parseQuestionRevisionDraft(value)
  const currentIndex = Math.min(questionIndex, Math.max(0, (draft?.questions.length ?? 0) - 1))
  const answered = draft?.answers.filter(answer => answer.trim()).length ?? 0
  const fileInputRef = useRef<HTMLInputElement>(null)
  const connections = useQuery({ queryKey: ['llmConnections', projectId, 'select'], queryFn: () => api.getLlmConnections(projectId!), enabled: Boolean(projectId) })
  const choices = listItems(connections.data).filter(item => item.status === 'active')
  const connectionId = choices.some(item => item.connectionId === selectedId) ? selectedId : choices.length === 1 ? choices[0].connectionId : undefined
  const busy = loading || uploading > 0
  const imageAttachments = attachments ?? []
  const attachmentsEnabled = Boolean(onAddAttachment && onRemoveAttachment)
  const sourceHint = sourceEditable ? '包含左侧尚未保存的修改，优化完成后仍需审核确认。' : '基于当前待审核产物重新生成，优化完成后仍需审核确认。'
  const canAdd = attachmentsEnabled && Boolean(projectId) && !loading && imageAttachments.length + uploading < MAX_ATTACHMENTS
  const actions = <div className="revision-footer-actions"><Button disabled={loading} onClick={onCancel}>取消优化</Button><ProjectActionButton action="execute" type="primary" loading={loading} disabled={busy || !connectionId || !revisionInstructionText(value)} onClick={() => connectionId && onSubmit(connectionId)}>提交优化</ProjectActionButton></div>

  async function uploadImages(files: File[]) {
    if (loading || !onAddAttachment) return
    if (!projectId) {
      message.error('请先选择项目后再添加图片')
      return
    }
    const remaining = Math.max(0, MAX_ATTACHMENTS - imageAttachments.length - uploading)
    if (remaining === 0) {
      message.warning(`最多添加 ${MAX_ATTACHMENTS} 张图片`)
      return
    }
    if (files.length > remaining) message.warning(`最多添加 ${MAX_ATTACHMENTS} 张图片，已忽略超出部分`)
    for (const file of files.slice(0, remaining)) {
      if (!IMAGE_TYPES.includes(file.type)) {
        message.error('图片仅支持 PNG 或 JPEG')
        continue
      }
      if (file.size > MAX_IMAGE_BYTES) {
        message.error(`单张图片不能超过 ${MAX_IMAGE_BYTES / 1024 / 1024} MB`)
        continue
      }
      setUploading(count => count + 1)
      try {
        const fileId = await uploadStoredFile(projectId, file, 'attachment')
        let previewUrl: string | undefined
        try {
          const { blob } = await downloadStoredFile(fileId)
          previewUrl = URL.createObjectURL(blob)
        } catch (error) {
          message.error(getErrorMessage(error))
        }
        onAddAttachment({ fileId, name: file.name, previewUrl })
      } catch (error) {
        message.error(getErrorMessage(error))
      } finally {
        setUploading(count => count - 1)
      }
    }
  }

  return <aside className="revision-side-panel" aria-label="继续优化" onPaste={event => {
    if (!attachmentsEnabled) return
    const files = Array.from(event.clipboardData?.files ?? []).filter(file => file.type.startsWith('image/'))
    if (!files.length || loading || !projectId || imageAttachments.length + uploading >= MAX_ATTACHMENTS) return
    event.preventDefault()
    void uploadImages(files)
  }}>
    <header><strong>继续优化</strong><span>对照左侧当前内容，补充修改要求</span></header>
    {draft && draft.questions.length > 0 ? <div className="revision-questions">
      <div className="revision-question-progress"><span>已填写 {answered} / {draft.questions.length}</span><span>未填写 {draft.questions.length - answered}</span></div>
      <div className="revision-question-track" aria-hidden="true"><span style={{ width: `${answered / draft.questions.length * 100}%` }} /></div>
      <div className="revision-question-nav" aria-label="问题列表">{draft.questions.map((question, index) => <button type="button" key={`${question.id}-${index}`} className={`${index === currentIndex ? 'is-current' : ''} ${draft.answers[index]?.trim() ? 'is-answered' : ''}`} aria-label={`问题 ${question.id}${draft.answers[index]?.trim() ? '，已填写' : ''}`} aria-current={index === currentIndex ? 'step' : undefined} onClick={() => setQuestionIndex(index)}>{index + 1}</button>)}</div>
      <div className="revision-question-content"><span className="revision-question-id">{draft.questions[currentIndex].id} · {draft.answers[currentIndex]?.trim() ? '已填写' : '待填写'}</span><p>{draft.questions[currentIndex].question}</p>
        <label htmlFor="revision-question-answer">补充答复</label><Input.TextArea id="revision-question-answer" aria-label="补充答复" rows={4} disabled={loading} value={draft.answers[currentIndex] ?? ''} placeholder="填写已确认的信息；暂时不清楚可留空" onChange={event => { const answers = [...draft.answers]; answers[currentIndex] = event.target.value; onChange(updateQuestionRevisionDraft({ ...draft, answers })) }} />
        <div className="revision-question-pagination"><Button disabled={currentIndex === 0} onClick={() => setQuestionIndex(currentIndex - 1)}>上一题</Button><Button disabled={currentIndex === draft.questions.length - 1} onClick={() => setQuestionIndex(currentIndex + 1)}>下一题</Button><span>{currentIndex + 1} / {draft.questions.length}</span></div></div>
      <details className="revision-question-extra"><summary>补充其他优化要求（可选）</summary><Input.TextArea aria-label="优化指令" rows={3} disabled={loading} value={draft.instruction} placeholder="填写其他优化要求" onChange={event => onChange(updateQuestionRevisionDraft({ ...draft, instruction: event.target.value }))} /></details>
    </div> : <>
    <label htmlFor="revision-side-instruction">优化指令</label>
    <Input.TextArea id="revision-side-instruction" aria-label="优化指令" value={draft?.instruction ?? value} disabled={loading} onChange={event => onChange(draft ? updateQuestionRevisionDraft({ ...draft, instruction: event.target.value }) : event.target.value)} placeholder={sourceEditable ? '请输入优化要求，将基于左侧当前编辑内容重新生成' : '请填写待确认问题的答复，或补充其他优化要求'} />
    </>}
    {attachmentsEnabled ? <>
      <div className="revision-attachments" role="group" aria-label="优化图片">
        {imageAttachments.map(attachment => <div className="revision-attachment" key={attachment.fileId} title={attachment.name}>
          {attachment.previewUrl ? <img src={attachment.previewUrl} alt={attachment.name} /> : <PictureOutlined aria-hidden="true" />}
          <button type="button" aria-label={`移除图片 ${attachment.name}`} disabled={loading} onClick={() => onRemoveAttachment?.(attachment.fileId)}>×</button>
        </div>)}
        <ActionButton operation="upload" size="small" disabled={!canAdd} onClick={() => fileInputRef.current?.click()}>添加图片</ActionButton>
        <input ref={fileInputRef} type="file" accept="image/png,image/jpeg" multiple hidden onChange={event => {
          const files = Array.from(event.target.files ?? [])
          event.target.value = ''
          if (files.length) void uploadImages(files)
        }} />
      </div>
      {uploading > 0 ? <span className="revision-side-hint">图片上传中…</span> : null}
      <span className="revision-side-hint">支持 PNG/JPEG，最多 {MAX_ATTACHMENTS} 张、单张 {MAX_IMAGE_BYTES / 1024 / 1024} MB，需所选模型支持图片输入；图片随本次优化提交，作为补充依据。{sourceHint}</span>
    </> : <span className="revision-side-hint">{sourceHint}</span>}
    <label>本次使用的模型</label>
    {connections.isLoading ? <Spin /> : connections.error ? <Alert type="error" showIcon title={getErrorMessage(connections.error)} /> : <Select aria-label="本次使用的模型" value={connectionId} disabled={loading} placeholder={choices.length ? '请选择本人 LLM 授权' : '暂无可用授权，请在基础服务中配置'} options={choices.map(item => ({ value: item.connectionId, label: `${item.name} · ${item.modelId}` }))} onChange={setSelectedId} />}
    {footerContainer === undefined ? actions : footerContainer ? createPortal(actions, footerContainer) : null}

  </aside>
}

export function RevisionDivider() {
  const resize = (handle: HTMLElement, width: number) => {
    const workspace = handle.parentElement
    const source = workspace?.querySelector<HTMLElement>(':scope > .revision-source')
    if (!workspace || !source) return
    source.style.setProperty('--revision-source-width', `${Math.max(35, Math.min(75, width / workspace.clientWidth * 100))}%`)
  }
  return <div className="revision-divider" role="separator" aria-label="调整原内容与优化面板宽度" aria-orientation="vertical" tabIndex={0}
    onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId) }}
    onPointerMove={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
      const left = event.currentTarget.parentElement?.getBoundingClientRect().left ?? 0
      resize(event.currentTarget, event.clientX - left)
    }}
    onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)}
    onKeyDown={event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      event.preventDefault()
      const source = event.currentTarget.parentElement?.querySelector<HTMLElement>(':scope > .revision-source')
      if (source) resize(event.currentTarget, source.clientWidth + (event.key === 'ArrowLeft' ? -30 : 30))
    }} />
}
