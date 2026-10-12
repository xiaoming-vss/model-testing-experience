import { useMemo } from 'react'
import { useStoredFileUrls } from '../files/useStoredFileUrls'
import { extractRichTextFileIds, injectImageSources } from './utils'
import '@/shared/styles/surface-tokens.css'
import './rich-text-editor.css'

/** 富文本只读渲染：按 data-file-id 鉴权下载，使用临时 Blob 地址展示。 */
export function RichTextViewer({
  html,
  className = '',
  ariaLabel = '富文本内容',
}: {
  html: string
  className?: string
  ariaLabel?: string
}) {
  const fileIds = useMemo(() => extractRichTextFileIds(html), [html])
  const { sources, errors, reload } = useStoredFileUrls(fileIds)

  const content = useMemo(() => injectImageSources(html, sources), [html, sources])

  if (!html.trim()) {
    return (
      <div className={`tp-surface rich-text-viewer is-empty ${className}`} aria-label={ariaLabel}>
        未填写内容
      </div>
    )
  }
  return <>
    {Object.keys(errors).length > 0 && <span role="alert">
      部分图片加载失败：{Object.values(errors)[0]}
      <button type="button" onClick={reload}>重新加载图片</button>
    </span>}
    <div
      className={`tp-surface rich-text-viewer ${className}`}
      aria-label={ariaLabel}
      // 内容在入库前已由服务端白名单消毒，这里只负责展示。
      dangerouslySetInnerHTML={{ __html: content }}
    />
  </>
}
