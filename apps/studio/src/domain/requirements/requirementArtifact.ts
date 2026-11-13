type RecordValue = Record<string, unknown>
export type RequirementSourceReference = { sourceId: string; locator: string; excerpt: string | null }
function record(value: unknown): value is RecordValue {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function parseRequirementArtifact(content: unknown): RecordValue | null {
  let parsed = content
  if (typeof content === 'string') {
    try { parsed = JSON.parse(content) } catch {
      if (content.trimStart().startsWith('{') && content.includes('"artifactType"') && /document_extraction|readable_requirement_material/.test(content)) {
        throw new Error('结构化需求无法解析，请在原始 JSON 中修正后保存')
      }
      return null
    }
  }
  if (!record(parsed) || !('artifactType' in parsed)) return null
  const versions: Record<string, string> = { readable_requirement_material: '0.2', document_extraction: '1.0' }
  if (!versions[String(parsed.artifactType)] || parsed.schemaVersion !== versions[String(parsed.artifactType)]) {
    throw new Error('当前产物版本或类型不受支持')
  }
  if (!Array.isArray(parsed.sources) || !Array.isArray(parsed.questions) ||
    (parsed.artifactType === 'document_extraction' && !Array.isArray(parsed.contentBlocks)) ||
    (parsed.artifactType === 'readable_requirement_material' && (!Array.isArray(parsed.materialBlocks) || !Array.isArray(parsed.functions)))) {
    throw new Error('结构化需求缺少必要业务内容，请修正后保存')
  }
  return parsed
}
