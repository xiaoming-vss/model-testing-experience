/** 富文本存储值的工具函数：只认 data-file-id，不保留任何图片 src。 */

export function extractRichTextFileIds(html: string): string[] {
  const ids: string[] = []
  const pattern = /data-file-id="([^"]+)"/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(html)) !== null) {
    if (!ids.includes(match[1])) ids.push(match[1])
  }
  return ids
}

/** 编辑器 HTML 输出前去掉临时预览 src，与后端消毒白名单保持一致。 */
export function stripImageSources(html: string): string {
  return html.replace(/(<img\b[^>]*?)\ssrc="[^"]*"/g, '$1')
}

/** 详情渲染前把 data-file-id 换成签名下载地址。 */
export function injectImageSources(html: string, sources: Record<string, string>): string {
  let output = html
  for (const [fileId, url] of Object.entries(sources)) {
    output = output.replaceAll(
      `data-file-id="${fileId}"`,
      `data-file-id="${fileId}" src="${url}"`,
    )
  }
  return output
}
