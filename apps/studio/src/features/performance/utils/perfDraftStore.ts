import type { PerfDataFile } from '../types'
import type { PerfCaseFormValues } from './perfCaseForm'

export type PerfCaseDraft = {
  yaml: string
  form: PerfCaseFormValues
  dataFiles: PerfDataFile[]
  savedAt: number
}

const drafts = new Map<string, PerfCaseDraft>()

export function getPerfCaseDraft(caseId: string) {
  return drafts.get(caseId)
}

export function setPerfCaseDraft(caseId: string, draft: Omit<PerfCaseDraft, 'savedAt'>) {
  drafts.set(caseId, { ...draft, savedAt: Date.now() })
}

export function clearPerfCaseDraft(caseId: string) {
  drafts.delete(caseId)
}
