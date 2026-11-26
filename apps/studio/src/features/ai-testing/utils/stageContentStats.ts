import { toRecord, toRecordArray } from '@/shared/utils/value'
import { caseVerificationCounts } from './historicalCaseVerificationView'
import { historicalRelationCounts, parseJsonRecord } from './historicalRelationView'

export type StageContentStat = [value: number, unit: string]

/** 阶段侧栏「内容概况」；只统计该阶段产物里真实存在的对象，没有可统计内容时返回 null。 */
export function stageContentStats(stage: string, content?: string | null, materialContent?: string | null): StageContentStat[] | null {
  if (!content) return null
  if (stage === 'historical_requirement_relations') return historicalRelationCounts(content)
  if (stage === 'historical_test_case_verification') return caseVerificationCounts(content, materialContent)
  if (stage !== 'extracting_text') return null
  const record = parseJsonRecord(content)
  if (!record) return null
  let sections = 0
  let rules = 0
  toRecordArray(record.functions).forEach((entry) => {
    const entrySections = Array.isArray(entry.sections) ? entry.sections : []
    sections += entrySections.length
    entrySections.forEach((section) => {
      const items = toRecord(section)?.items
      if (Array.isArray(items)) rules += items.length
    })
  })
  const questions = Array.isArray(record.questions) ? record.questions.length : 0
  return sections || rules || questions
    ? [[sections, '个章节'], [rules, '条规则'], [questions, '个待确认']]
    : null
}
