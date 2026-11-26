import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useProjectRequirementOptions } from '@/domain/projects/hooks/useProjectRequirementOptions'
import { api, listItems } from '@/services/api'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { cx } from '@/shared/utils/cx'
import { normalizeFunctionTestSuiteId } from '@/utils/format'
import { buildCaseVerification } from '../../utils/historicalCaseVerificationView'
import { DETAIL_INNER, DETAIL_SCROLL } from '../TestScopeAnalysisView/testScopeClasses'
import { SPLIT_ROOT } from '../HistoricalRelationView/historicalRelationClasses'
import { useReadingDetailScroll } from '../readingDetailScroll'
import { HistoricalCaseVerificationDetail } from './CaseVerificationDetail'
import { HistoricalCaseVerificationRail } from './HistoricalCaseVerificationRail'
import { verificationListing, type VerificationCategory, type VerificationFilter } from './verificationListing'
import type { VerificationLookup } from './RuleVerificationDetail'

const EMPTY_TEXT = {
  rules: '当前筛选下没有规则。',
  cases: '暂无需要维护的历史用例。',
  points: '没有补测测试点。',
  pending: '没有待确认的用例。',
} as const
const NO_BATCH = '本次没有需要核验的规则变更或新增场景。'

/**
 * 历史用例核验默认查看待维护用例，按需打开规则、补测测试点和待确认档案。
 * 规则原文和用例全文来自冻结的阶段输入（materialContent）；需求名称与测试集名称按项目查找。
 */
export function HistoricalCaseVerificationView({ content, materialContent, projectId }: {
  content: string
  materialContent?: string | null
  projectId: string
}) {
  const { requirementNameMap } = useProjectRequirementOptions({ activeProjectId: projectId })
  const suitesQuery = useQuery({ queryKey: ['caseVerificationSuites', projectId], queryFn: () => api.getProjectFunctionTestSuites(projectId) })
  const suiteNames = useMemo(
    () => new Map(listItems(suitesQuery.data).map(suite => [normalizeFunctionTestSuiteId(suite), suite.name])),
    [suitesQuery.data],
  )
  const data = useMemo(() => buildCaseVerification(content, materialContent), [content, materialContent])
  const [category, setCategory] = useState<VerificationCategory>('cases')
  const [filter, setFilter] = useState<VerificationFilter>('all')
  const [selectedIds, setSelectedIds] = useState<Partial<Record<VerificationCategory, string>>>({})
  const [focusFinding, setFocusFinding] = useState<string | null>(null)
  /** 用户手动开关过的结论；切换规则或分类后清空，回到自动展开。 */
  const [manual, setManual] = useState<Record<string, boolean>>({})
  const resetManual = () => setManual({})

  const items = data ? verificationListing(category, data, filter) : []
  const active = items.find(item => item.id === selectedIds[category]) ?? items[0]
  const batch = category === 'rules' ? data?.batches.find(item => item.id === active?.id) : undefined
  // 进入或切换规则时自动展开首条可批注的结论，从其他档案跳回时展开指向的那一条。
  // 展开状态在渲染时派生：跳回后的滚动定位要落在已展开的内容上，放进 effect 会晚一步。
  const annotated = (batch?.findings ?? []).filter(finding => finding.snapshot)
  const autoOpen = annotated.find(finding => finding.id === focusFinding) ?? annotated[0]
  const isExpanded = (id: string) => manual[id] ?? id === autoOpen?.id
  const { detailRef, scrollOnSelectionRef } = useReadingDetailScroll(
    `${category}:${active?.id}`,
    category === 'rules' && focusFinding ? { attribute: 'data-finding-id', value: focusFinding } : null,
  )

  // 只在内容变化时重置浏览状态；需求摘要或测试集名称刷新时不应打断阅读。
  useEffect(() => {
    setCategory('cases')
    setFilter('all')
    setSelectedIds({})
    setFocusFinding(null)
  }, [content, materialContent])

  if (!data) return <ListEmptyState className="h-full" description="历史用例核验结果格式无效，请重新生成" />

  const emptyText = data.batches.length ? EMPTY_TEXT[category] : NO_BATCH
  const lookup: VerificationLookup = {
    requirementName: (id) => requirementNameMap.get(id) ?? id,
    suiteName: (suiteId) => suiteNames.get(suiteId) ?? suiteId,
    caseFindings: (caseId) => data.findings.filter(item => item.caseId === caseId),
    isExpanded,
    toggle: (id) => setManual((current) => ({ ...current, [id]: !isExpanded(id) })),
    openRule: (batchId, findingId) => {
      setCategory('rules')
      setFilter('all')
      setSelectedIds({ rules: batchId })
      setFocusFinding(findingId ?? null)
      resetManual()
    },
  }

  return <div className={SPLIT_ROOT}>
    <HistoricalCaseVerificationRail
      category={category}
      data={data}
      items={items}
      activeId={active?.id}
      filter={filter}
      emptyText={emptyText}
      onCategory={(next) => { setCategory(next); setFilter('all'); resetManual() }}
      onFilter={setFilter}
      onSelect={(id) => {
        scrollOnSelectionRef.current = true
        resetManual()
        setSelectedIds((current) => ({ ...current, [category]: id }))
      }}
    />
    <div ref={detailRef} className={cx(DETAIL_SCROLL, 'scroll-mt-2')}>
      {active
        ? <div className={DETAIL_INNER}>
            <HistoricalCaseVerificationDetail
              key={`${category}:${active.id}`}
              category={category}
              batch={batch}
              item={data.cases.find(item => item.caseId === active.id)}
              point={data.points.find(item => item.id === active.id)}
              pending={data.findings.find(item => item.id === active.id)}
              lookup={lookup}
            />
          </div>
        : <ListEmptyState className="h-full" description={emptyText} />}
    </div>
  </div>
}
