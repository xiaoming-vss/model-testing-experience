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
  const questions = analysis?.questions ?? analysis?.openQuestions
  if (!Array.isArray(questions)) return []
  return questions.flatMap((item, index) => {
    const row = objectValue(item)
    if (row?.status === 'resolved' || typeof row?.question !== 'string' || !row.question.trim()) return []
    const id = row.id ?? row.questionId
    return [{ id: typeof id === 'string' && id.trim() ? id.trim() : `Q${String(index + 1).padStart(2, '0')}`, question: row.question.trim() }]
  })
}

export function revisionQuestionHeading(question: RevisionQuestion): string {
  return `【${question.id}】${question.question}`
}

export function buildRevisionTemplate(questions: RevisionQuestion[], stageLabel: string, answerLabel = '补充'): string {
  if (!questions.length) return ''
  return [
    `请根据以下补充信息优化当前${stageLabel}：`,
    '仅依据已补充的信息修订；未填写或仍为占位文字的项目继续保留为待确认，不要推测答案。',
    ...questions.map((question) => `${revisionQuestionHeading(question)}\n${answerLabel}：[请填写已确认的信息]`),
  ].join('\n\n')
}
