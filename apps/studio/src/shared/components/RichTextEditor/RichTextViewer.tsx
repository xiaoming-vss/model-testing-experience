import { useEffect, useMemo, useState } from 'react'
import { request } from '@/shared/api/request'
import { extractRichTextFileIds, injectImageSources } from './utils'
import './rich-text-editor.css'

type UploadTicket = { url: string }

/** 富文本只读渲染：按 data-file-id 现取签名地址再加载图片。 */
export function RichTextViewer({
  html,
  className = '',
  ariaLabel = '富文本内容',
}: {
  html: string
  className?: string
  ariaLabel?: string
}) {
  const [sources, setSources] = useState<Record<string, string>>({})
  const fileIds = useMemo(() => extractRichTextFileIds(html), [html])
  const fileIdsKey = fileIds.join(',')

  useEffect(() => {
    if (fileIdsKey.length === 0) return
    let cancelled = false
    setSources({})
    fileIds.forEach((fileId) => {
      request<UploadTicket>(`/v1/files/${fileId}/download`)
        .then((ticket) => {
          if (!cancelled) setSources((previous) => ({ ...previous, [fileId]: ticket.url }))
        })
        .catch(() => {
          // 签名地址取不到时保持无 src，由样式展示占位，不阻塞正文阅读。
        })
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileIdsKey])

  const content = useMemo(() => injectImageSources(html, sources), [html, sources])

  if (!html.trim()) {
    return (
      <div className={`rich-text-viewer is-empty ${className}`} aria-label={ariaLabel}>
        未填写内容
      </div>
    )
  }
  return (
    <div
      className={`rich-text-viewer ${className}`}
      aria-label={ariaLabel}
      // 内容在入库前已由服务端白名单消毒，这里只负责展示。
      dangerouslySetInnerHTML={{ __html: content }}
    />
  )
}
