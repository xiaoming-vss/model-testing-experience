import type { ReactNode } from 'react'
import { cx } from '@/shared/utils/cx'
import {
  batchTitle, caseRank, decisionTags, findingTitle, type CaseVerificationData, type MaintenanceDecision,
} from '../../utils/historicalCaseVerificationView'
import { HistoricalTag } from '../HistoricalRelationView/HistoricalTag'
import { STATUS_DOT, STATUS_PLAIN } from '../TestScopeAnalysisView/testScopeClasses'
import { DOT } from './historicalCaseVerificationClasses'

export type VerificationCategory = 'rules' | 'cases' | 'points' | 'pending'
export type VerificationFilter = 'all' | 'todo' | 'clear' | MaintenanceDecision
export type VerificationListItem = { id: string; lead: string; name: string; status: ReactNode }

const rulesOf = (data: CaseVerificationData, filter: VerificationFilter) => data.batches.filter(batch => filter === 'all'
  || (batch.findings.length > 0) === (filter === 'todo'))
const casesOf = (data: CaseVerificationData, filter: VerificationFilter) => data.cases
  .filter(item => filter === 'all' || item.findings.some(finding => finding.decision.key === filter))
  .sort((a, b) => caseRank(a) - caseRank(b))

/** 各分类的导航列表；首列统一是结论数或场景序号。 */
export function verificationListing(category: VerificationCategory, data: CaseVerificationData, filter: VerificationFilter): VerificationListItem[] {
  if (category === 'rules') {
    return rulesOf(data, filter).map(batch => ({
      id: batch.id, lead: String(batch.findings.length), name: batchTitle(batch),
      status: batch.effect ? <HistoricalTag value={batch.effect} /> : null,
    }))
  }
  if (category === 'cases') {
    return casesOf(data, filter).map(item => ({
        id: item.caseId, lead: String(item.findings.length), name: findingTitle(item.findings[0]),
        status: decisionTags(item.findings).map(decision => (
          <span key={decision.key} className={STATUS_PLAIN}>
            <span className={cx(STATUS_DOT, DOT[decision.tone])} aria-hidden="true" />
            {decision.label}
          </span>
        )),
    }))
  }
  if (category === 'points') {
    return data.points.map(point => ({
      id: point.id, lead: String(point.order), name: point.title, status: null,
    }))
  }
  return data.findings.filter(finding => finding.decision.key === 'needs_confirmation').map((finding, index) => ({
    id: finding.id, lead: String(index + 1), name: findingTitle(finding), status: <HistoricalTag value={finding.decision} />,
  }))
}
