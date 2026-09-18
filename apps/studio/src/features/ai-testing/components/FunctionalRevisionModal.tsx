import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { FullscreenExitOutlined, FullscreenOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Input, Modal, Tag, theme } from 'antd'
import type { TextAreaRef } from 'antd/es/input/TextArea'
import { useRef, useState } from 'react'
import { revisionQuestionHeading, type RevisionQuestion } from '../utils/functionalRevision'
import './FunctionalRevisionModal.css'

type Props = {
  open: boolean
  taskName: string
  stageLabel: string
  questions: RevisionQuestion[]
  value: string
  loading: boolean
  onChange: (value: string) => void
  onCancel: () => void
  onSubmit: () => void
}

export function FunctionalRevisionModal({ open, taskName, stageLabel, questions, value, loading, onChange, onCancel, onSubmit }: Props) {
  const { token } = theme.useToken()
  const [fullscreen, setFullscreen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<TextAreaRef>(null)

  function locateQuestion(index: number) {
    setActiveIndex(index)
    const input = inputRef.current?.resizableTextArea?.textArea
    if (!input) return
    const start = value.indexOf(revisionQuestionHeading(questions[index]))
    input.focus()
    if (start < 0) return
    const answerStart = start + revisionQuestionHeading(questions[index]).length + '\n补充：'.length
    const position = Math.min(answerStart, value.length)
    input.setSelectionRange(position, position)
    const lineHeight = parseFloat(getComputedStyle(input).lineHeight) || 28
    input.scrollTop = Math.max(0, (value.slice(0, position).split('\n').length - 2) * lineHeight)
  }

  return (
    <Modal
      title={<div className="functional-revision-title"><span>继续优化</span><Tag color="blue">{stageLabel}</Tag></div>}
      className={`functional-revision-modal${fullscreen ? ' is-fullscreen' : ''}`}
      zIndex={token.zIndexPopupBase + 200}
      open={open}
      width={fullscreen ? 'calc(100vw - 32px)' : 'min(1100px, calc(100vw - 48px))'}
      centered={!fullscreen}
      style={fullscreen ? { top: 16, paddingBottom: 0 } : undefined}
      mask={{ closable: false }}
      closable={!loading}
      onCancel={() => { if (!loading) onCancel() }}
      footer={<div className="functional-revision-footer">
        <span>基于当前编辑内容优化，完成后仍需确认</span>
        <div><Button disabled={loading} onClick={onCancel}>取消</Button><ProjectActionButton action="execute" type="primary" loading={loading} onClick={onSubmit}>提交优化</ProjectActionButton></div>
      </div>}
      afterOpenChange={(visible) => { if (visible) inputRef.current?.focus() }}
    >
      <Button className="functional-revision-expand" type="text" aria-label={fullscreen ? '退出全屏' : '全屏展开'}
        icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={() => setFullscreen(!fullscreen)} />
      <div className="functional-revision-task">{taskName}</div>
      <Alert showIcon type="info" title={questions.length
        ? `已自动带入 ${questions.length} 个待确认项，请补充已知信息；未填写的项目将继续保留为待确认。`
        : '请填写本阶段需要补充或调整的内容。'} />
      <div className="functional-revision-content">
        <aside className="functional-revision-questions" aria-label="待确认项列表">
          <div className="functional-revision-section-heading"><strong>待确认项 <Tag color="blue">{questions.length}</Tag></strong><span>来自本次分析</span></div>
          <div className="functional-revision-question-list">
            {questions.length ? questions.map((question, index) => (
              <button type="button" key={`${question.id}-${index}`} disabled={loading}
                className={`functional-revision-question${index === activeIndex ? ' is-active' : ''}`}
                aria-current={index === activeIndex ? 'true' : undefined}
                onClick={() => locateQuestion(index)}>
                <Tag color="blue">{question.id}</Tag><span>{question.question}</span>
              </button>
            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待确认项" />}
          </div>
        </aside>
        <section className="functional-revision-editor">
          <div><strong>优化指令</strong><p>{questions.length ? '问题已预填，可直接补充或修改' : '填写你希望补充或调整的内容'}</p></div>
          <Input.TextArea ref={inputRef} aria-label="优化指令" value={value} disabled={loading}
            onChange={(event) => onChange(event.target.value)} placeholder="请输入优化要求，将基于当前编辑内容重新生成" />
          <span className="functional-revision-hint">可追加其他优化要求；不会自动生成未经确认的答案。</span>
        </section>
      </div>
    </Modal>
  )
}
