import { BugDetailPanel } from './BugDetailPanel'
import { useState } from 'react'
import { Button, Alert } from 'antd'
import { DownloadOutlined, FileOutlined } from '@ant-design/icons'
import { useStoredFileUrls } from '@/shared/components/files/useStoredFileUrls'
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
  const preview = useStoredFileUrls(selected ? [selected.fileId] : [])
  return <BugDetailPanel>
    <h2 className="bug-panel-title mb-4 flex items-center gap-2 border-b border-[var(--srf-divider)] pb-3 text-[14px] font-semibold text-[var(--srf-text)]">附件与多媒体凭据 <span className="bug-section-count text-xs font-normal text-[var(--srf-text-muted)]">{files.length} 个附件</span></h2>
    {!files.length ? <span className="bug-detail-subtitle text-xs text-[var(--srf-text-muted)]">暂无附件</span> : <div className={`bug-evidence-layout grid gap-4 ${selected ? 'has-preview grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] max-[720.01px]:grid-cols-1' : ''}`}>
      {selected && <div className="bug-evidence-preview min-w-0 rounded-[8px] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-3 [&_img]:mt-3 [&_img]:block [&_img]:max-h-[360px] [&_img]:w-full [&_img]:object-contain [&_video]:mt-3 [&_video]:block [&_video]:max-h-[360px] [&_video]:w-full [&_video]:object-contain">
        <div className="bug-evidence-caption flex items-center justify-between gap-2 break-words text-xs text-[var(--srf-text-secondary)]">{selected.filename}<Button type="text" size="small" onClick={() => setSelectedId(undefined)}>收起预览</Button></div>
        {preview.errors[selected.fileId] ? <Alert type="error" title="预览加载失败" action={<Button onClick={preview.reload}>重试</Button>} />
          : preview.sources[selected.fileId] ? selected.contentType.startsWith('video/')
            ? <video key={selected.fileId} src={preview.sources[selected.fileId]} controls preload="metadata" aria-label={selected.filename} />
            : <img src={preview.sources[selected.fileId]} alt={selected.filename} />
          : <span>正在加载预览…</span>}
      </div>}
      <ul className="bug-evidence-files m-0 flex list-none flex-col gap-2.5 p-0">{files.map((item) => <li key={item.fileId} className="flex min-w-0 items-center gap-2.5 rounded-[6px] border border-[var(--srf-card-border)] p-3">
        <span className="bug-evidence-icon inline-flex h-9 w-9 flex-none items-center justify-center rounded-[6px] bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]"><FileOutlined /></span>
        <div className="bug-evidence-file-info min-w-0 flex-1 text-xs [&>button]:block [&>button]:max-w-full [&>button]:cursor-pointer [&>button]:overflow-hidden [&>button]:border-0 [&>button]:bg-transparent [&>button]:p-0 [&>button]:text-left [&>button]:text-ellipsis [&>button]:whitespace-nowrap [&>button]:text-[var(--srf-accent)] [&>span]:block [&>span]:max-w-full [&>span]:overflow-hidden [&>span]:text-ellipsis [&>span]:whitespace-nowrap [&_small]:mt-1 [&_small]:block [&_small]:text-[var(--srf-text-muted)]">
          {media.includes(item) ? <button type="button" aria-expanded={selected?.fileId === item.fileId} onClick={() => setSelectedId(selectedId === item.fileId ? undefined : item.fileId)} title={item.filename}>{item.filename}</button>
            : <span title={item.filename}>{item.filename}</span>}
          <small>{(item.size / 1024).toFixed(1)} KB</small>
        </div>
        <Button type="text" size="small" icon={<DownloadOutlined />} aria-label={`下载 ${item.filename}`} onClick={() => void download(item.fileId, item.filename)} />
      </li>)}</ul>
    </div>}
  </BugDetailPanel>
}
