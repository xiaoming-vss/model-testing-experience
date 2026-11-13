/** JSON 产物在原文视图统一展开缩进，避免待审核草稿以单行压缩 JSON 出现。 */
export function formatJsonArtifact(content: string): string {
  if (!content.trim()) return content
  const trimmed = content.trimStart()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return content
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
}

/** 按产物语言格式化原文：JSON 展开缩进，YAML/纯文本保持原样。 */
export function formatRawArtifact(content: string, label: string): string {
  return label === 'JSON' ? formatJsonArtifact(content) : content
}
