import { useEffect, useMemo, useState } from 'react'
import { useProjectRequirementOptions } from '@/domain/projects/hooks/useProjectRequirementOptions'
import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { cx } from '@/shared/utils/cx'
import {
  buildHistoricalRelationView,
  type HistoricalImpactView,
  type HistoricalRelationView,
  type HistoricalQuestionView,
} from '../../utils/historicalRelationView'
import { DETAIL_INNER, DETAIL_SCROLL } from '../TestScopeAnalysisView/testScopeClasses'
import { useReadingDetailScroll } from '../readingDetailScroll'
import { HistoricalRelationDetail } from './HistoricalRelationDetail'
import {
  HistoricalRelationRail,
  type HistoricalRelationCategory,
  type HistoricalRelationFilter,
} from './HistoricalRelationRail'
import { SPLIT_ROOT } from './historicalRelationClasses'

/**
 * 历史需求关联的可视化阅读：左侧按关联需求和待确认导航，右侧只读地阅读关联档案。
 * 条目原文来自冻结的阶段输入（materialContent）；需求名称与迭代按项目需求摘要查找。
 */
export function HistoricalRelationView({ content, materialContent, projectId }: {
  content: string
  materialContent?: string | null
  projectId: string
}) {
  const { requirementNameMap, requirementSprintMap, sprintNameMap } = useProjectRequirementOptions({ activeProjectId: projectId })
  const view = useMemo(() => buildHistoricalRelationView(content, materialContent, (id) => ({
    name: requirementNameMap.get(id) ?? id,
    sprintName: sprintNameMap.get(requirementSprintMap.get(id) ?? '') ?? '',
  })), [content, materialContent, requirementNameMap, requirementSprintMap, sprintNameMap])
  const [category, setCategory] = useState<HistoricalRelationCategory>('relations')
  const [filter, setFilter] = useState<HistoricalRelationFilter>('all')
  const [selectedIds, setSelectedIds] = useState<Partial<Record<HistoricalRelationCategory, string>>>({})
  const [focusImpact, setFocusImpact] = useState<HistoricalImpactView | null>(null)

  const matched = category === 'relations'
    ? view?.relations.filter((relation) => filter === 'all' || relation.type.key === filter) ?? []
    : view?.questions.filter((question) => filter === 'all' || (filter === 'linked') === Boolean(question.impact)) ?? []
  const active = matched.find((item) => item.id === selectedIds[category]) ?? matched[0]
  const { detailRef, scrollOnSelectionRef } = useReadingDetailScroll(
    `${category}:${active?.id}`,
    focusImpact ? { attribute: 'data-impact-id', value: focusImpact.id } : null,
  )

  // 只在内容变化时重置浏览状态；需求摘要刷新导致视图对象重建时不应打断阅读。
  useEffect(() => {
    setFilter('all')
    setSelectedIds({})
    setFocusImpact(null)
  }, [content, materialContent])

  if (!view) return <ListEmptyState className="h-full" description="历史需求关联结果格式无效，请重新生成" />

  // 筛选芯片计数为 0 时禁用，所以列表为空只可能是产物本身没有这一类内容。
  const emptyText = category === 'relations'
    ? view.questions.length
      ? `没有可关联的历史需求；仍有 ${view.questions.length} 个待确认问题，可在导航栏切换查看。`
      : '没有可关联的历史需求。'
    : '本次分析没有记录待确认问题。'
  const relation = category === 'relations' ? active as HistoricalRelationView | undefined : undefined
  const question = category === 'questions' ? active as HistoricalQuestionView | undefined : undefined

  return <div className={SPLIT_ROOT}>
    <HistoricalRelationRail
      category={category}
      data={view}
      items={matched}
      activeId={active?.id}
      filter={filter}
      emptyText={emptyText}
      onCategory={(next) => { setCategory(next); setFilter('all') }}
      onFilter={setFilter}
      onSelect={(id) => {
        scrollOnSelectionRef.current = true
        setSelectedIds((current) => ({ ...current, [category]: id }))
      }}
    />
    <div ref={detailRef} className={cx(DETAIL_SCROLL, 'scroll-mt-2')}>
      {active
        ? <div className={DETAIL_INNER}>
            <HistoricalRelationDetail
              key={`${category}:${active.id}`}
              category={category}
              relation={relation}
              question={question}
              data={view}
              requirementName={(id) => requirementNameMap.get(id) ?? id}
              onJumpQuestion={(target) => { setCategory('questions'); setFilter('all'); setSelectedIds({ questions: target.id }) }}
              onJumpImpact={(target) => {
                setCategory('relations')
                setFilter('all')
                setSelectedIds({ relations: target.relation.id })
                setFocusImpact(target)
              }}
            />
          </div>
        : <ListEmptyState className="h-full" description={emptyText} />}
    </div>
  </div>
}
