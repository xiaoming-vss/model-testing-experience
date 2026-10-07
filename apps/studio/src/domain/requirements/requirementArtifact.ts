type RecordValue = Record<string, unknown>
export type RequirementSourceReference = { sourceId: string; locator: string; excerpt: string | null }
function record(value: unknown): value is RecordValue {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function parseRequirementArtifact(content: unknown): RecordValue | null {
  let parsed = content
  if (typeof content === 'string') {
    try { parsed = JSON.parse(content) } catch {
      if (content.trimStart().startsWith('{') && content.includes('"artifactType"') && /document_extraction|requirement_understanding/.test(content)) {
        throw new Error('结构化需求无法解析，请在原始 JSON 中修正后保存')
      }
      return null
    }
  }
  if (!record(parsed) || !('artifactType' in parsed)) return null
  if (parsed.schemaVersion !== '1.0' || !['document_extraction', 'requirement_understanding'].includes(String(parsed.artifactType))) {
    throw new Error('当前产物版本或类型不受支持')
  }
  if (!Array.isArray(parsed.sources) || !Array.isArray(parsed.questions) ||
    (parsed.artifactType === 'requirement_understanding' && !Array.isArray(parsed.modules)) ||
    (parsed.artifactType === 'document_extraction' && !Array.isArray(parsed.contentBlocks))) {
    throw new Error('结构化需求缺少必要业务内容，请修正后保存')
  }
  return parsed
}


/** Resolved entries in earlier artifacts are not pending work. JSON editing remains lossless. */
export function pendingRequirementQuestions<T extends Record<string, unknown>>(questions: T[]): T[] {
  return questions.filter(question => question.status !== 'resolved')
}
