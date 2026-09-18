export type RevisionQuestion = { id: string; question: string }

function objectValue(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === 'string') {
    try { return objectValue(JSON.parse(value)) } catch { return undefined }
  }
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}

export function getRevisionQuestions(value: unknown): RevisionQuestion[] {
  const record = objectValue(value)
  const analysis = objectValue(record?.requirementAnalysis) ?? record
  if (!Array.isArray(analysis?.openQuestions)) return []
  return analysis.openQuestions.flatMap((item, index) => {
    const row = objectValue(item)
    if (typeof row?.question !== 'string' || !row.question.trim()) return []
    return [{ id: typeof row.questionId === 'string' && row.questionId.trim() ? row.questionId.trim() : `Q${String(index + 1).padStart(2, '0')}`, question: row.question.trim() }]
  })
}

export function revisionQuestionHeading(question: RevisionQuestion): string {
  return `【${question.id}】${question.question}`
}

export function buildRevisionTemplate(questions: RevisionQuestion[], stageLabel: string): string {
  if (!questions.length) return ''
  return [
    `请根据以下补充信息优化当前${stageLabel}：`,
    '仅依据已补充的信息修订；未填写或仍为占位文字的项目继续保留为待确认，不要推测答案。',
    ...questions.map((question) => `${revisionQuestionHeading(question)}\n补充：[请填写已确认的信息]`),
  ].join('\n\n')
}
