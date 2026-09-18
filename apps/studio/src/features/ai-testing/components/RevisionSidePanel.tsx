import { Alert, Button, Input, Select, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { api, listItems } from '@/services/api'
import { getErrorMessage } from '@/utils/format'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import './RevisionSidePanel.css'

type Props = {
  footerContainer?: HTMLElement | null
  projectId?: string
  value: string
  onChange: (value: string) => void
  onSubmit: (connectionId: string) => void
  onCancel: () => void
  loading: boolean
}

export function RevisionSidePanel({ footerContainer, projectId, value, onChange, onSubmit, onCancel, loading }: Props) {
  const [selectedId, setSelectedId] = useState<string>()
  const connections = useQuery({ queryKey: ['llmConnections', projectId, 'select'], queryFn: () => api.getLlmConnections(projectId!), enabled: Boolean(projectId) })
  const choices = listItems(connections.data).filter(item => item.status === 'active')
  const connectionId = choices.some(item => item.connectionId === selectedId) ? selectedId : choices.length === 1 ? choices[0].connectionId : undefined
  const actions = <div className="revision-footer-actions"><Button disabled={loading} onClick={onCancel}>取消优化</Button><ProjectActionButton action="execute" type="primary" loading={loading} disabled={!connectionId || !value.trim()} onClick={() => connectionId && onSubmit(connectionId)}>提交优化</ProjectActionButton></div>
  return <aside className="revision-side-panel" aria-label="继续优化">
    <header><strong>继续优化</strong><span>对照左侧当前内容，补充修改要求</span></header>
    <label htmlFor="revision-side-instruction">优化指令</label>
    <Input.TextArea id="revision-side-instruction" aria-label="优化指令" value={value} disabled={loading} onChange={event => onChange(event.target.value)} placeholder="请输入优化要求，将基于左侧当前编辑内容重新生成" />
    <span className="revision-side-hint">包含左侧尚未保存的修改，优化完成后仍需审核确认。</span>
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
