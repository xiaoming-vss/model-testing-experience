import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Alert } from 'antd'
import { DownloadOutlined, FileOutlined } from '@ant-design/icons'
import { api } from '@/services/api'
import type { BugAttachment } from '../types'

export function BugEvidencePanel({ attachments, descriptionHtml = '', download }: {
  attachments: BugAttachment[]; descriptionHtml?: string; download: (id: string, filename: string) => Promise<void>
}) {
  const description = new DOMParser().parseFromString(descriptionHtml, 'text/html')
  const inlineFileIds = new Set(Array.from(description.querySelectorAll('[data-file-id]'), (node) => node.getAttribute('data-file-id')))
  const files = attachments.filter((item) => !inlineFileIds.has(item.fileId))
  const media = files.filter((item) => /^(image\/(png|jpeg|gif|webp)|video\/(mp4|webm))$/.test(item.contentType))
  const [selectedId, setSelectedId] = useState<string>()
  const selected = media.find((item) => item.fileId === selectedId)
  const preview = useQuery({ queryKey: ['bugAttachmentPreview', selected?.fileId],
    queryFn: () => api.downloadAttachment(selected!.fileId), enabled: Boolean(selected), staleTime: 0 })
  return <section className="bug-detail-panel">
    <h2 className="bug-panel-title">附件与多媒体凭据 <span className="bug-section-count">{files.length} 个附件</span></h2>
    {!files.length ? <span className="bug-detail-subtitle">暂无附件</span> : <div className={`bug-evidence-layout${selected ? ' has-preview' : ''}`}>
      {selected && <div className="bug-evidence-preview">
        <div className="bug-evidence-caption">{selected.filename}<Button type="text" size="small" onClick={() => setSelectedId(undefined)}>收起预览</Button></div>
        {preview.isError ? <Alert type="error" title="预览加载失败" action={<Button onClick={() => preview.refetch()}>重试</Button>} />
          : preview.data ? selected.contentType.startsWith('video/')
            ? <video key={selected.fileId} src={preview.data.url} controls preload="metadata" aria-label={selected.filename} />
            : <img src={preview.data.url} alt={selected.filename} />
          : <span>正在加载预览…</span>}
      </div>}
      <ul className="bug-evidence-files">{files.map((item) => <li key={item.fileId}>
        <span className="bug-evidence-icon"><FileOutlined /></span>
        <div className="bug-evidence-file-info">
          {media.includes(item) ? <button type="button" aria-expanded={selected?.fileId === item.fileId} onClick={() => setSelectedId(selectedId === item.fileId ? undefined : item.fileId)} title={item.filename}>{item.filename}</button>
            : <span title={item.filename}>{item.filename}</span>}
          <small>{(item.size / 1024).toFixed(1)} KB</small>
        </div>
        <Button type="text" size="small" icon={<DownloadOutlined />} aria-label={`下载 ${item.filename}`} onClick={() => void download(item.fileId, item.filename)} />
      </li>)}</ul>
    </div>}
  </section>
}
