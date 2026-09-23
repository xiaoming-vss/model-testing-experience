import { Alert, Empty } from 'antd'

import { useMemo, useRef, useState } from 'react'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { UiSuiteListBanner } from '@/features/ui-automation/components/UiSuiteListBanner'
import { UiSuiteListToolbar } from '@/features/ui-automation/components/UiSuiteListToolbar'
import { UiTestSuiteSection, type UiTestSuiteSectionRef } from '@/features/ui-automation/components/UiTestSuiteSection'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import type { Requirement } from '@/services/api'
import { getErrorMessage, normalizeRequirementId, normalizeSprintId } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/features/ui-automation/styles/list-v2.css'

type UiAutomationPageScope = {
  projectId?: string
  sprintId?: string
  sprintName?: string
  requirementId?: string
  requirementName?: string
}

export function UiAutomationPage({ scope }: { scope?: UiAutomationPageScope }) {
  const workbenchActiveProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const activeProjectId = scope?.projectId ?? workbenchActiveProjectId
  const uiTestSuiteSectionRef = useRef<UiTestSuiteSectionRef | null>(null)
  const [keyword, setKeyword] = useState('')
  // 刷新按钮的加载态由持有查询的 UiTestSuiteSection 回传，页面只负责显示。
  const [refreshing, setRefreshing] = useState(false)
  const isRequirementLocked = Boolean(scope?.requirementId)
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()
  const {
    currentRequirementSelection,
    currentSprintSelection,
    requirementFilterOptions,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
    sprintFilterOptions,
    sprints,
    sprintsQuery,
  } = useSprintRequirementScope({
    activeProjectId,
    includeAllRequirementOption: true,
    includeAllSprintOption: true,
    defaultToAllWhenIncluded: true,
    sprintScope: scope ? undefined : { value: globalSprintId, onChange: selectGlobalSprint },
  })
  const selectedSprintId = scope?.sprintId ?? resolvedSelectedSprintId
  const selectedRequirementId = scope?.requirementId ?? resolvedSelectedRequirementId
  const { allRequirements, allRequirementsQuery, requirementNameMap, requirementSprintMap, sprintNameMap } =
    useProjectRequirements({
      activeProjectId,
      enabled: !sprintsQuery.isLoading && !isRequirementLocked,
      sprints,
    })
  const displayRequirementFilterOptions = useMemo(() => {
    if (selectedSprintId) return requirementFilterOptions
    return [
      { label: '全部需求', value: 'all' },
      ...allRequirements.map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    ]
  }, [allRequirements, requirementFilterOptions, selectedSprintId])
  const drawerSprintOptions = useMemo(
    () => sprints.map((sprint) => ({ label: sprint.name, value: normalizeSprintId(sprint) })),
    [sprints],
  )
  const visibleRequirementIds = useMemo(() => {
    if (selectedRequirementId) return [selectedRequirementId]
    const targetRequirements: Requirement[] = selectedSprintId
      ? allRequirements.filter((item) => (item.sprintId ?? item.sprint_id) === selectedSprintId)
      : allRequirements
    return targetRequirements.map(normalizeRequirementId)
  }, [allRequirements, selectedRequirementId, selectedSprintId])
  const canCreateSuite = Boolean(activeProjectId) && sprints.length > 0
  return (
    <div className="workbench-page api-automation-page functional-test-page ui-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          <UiSuiteListBanner />

          <UiSuiteListToolbar
            showScopeFilters={!isRequirementLocked}
            sprintValue={currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'}
            sprintOptions={sprintFilterOptions}
            sprintLoading={sprintsQuery.isLoading}
            onSprintChange={(value: string) => {
              selectSprint(value === 'all' ? null : value)
              if (value === 'all') {
                selectRequirement(null)
              }
            }}
            requirementValue={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
            requirementOptions={displayRequirementFilterOptions}
            requirementLoading={requirementsQuery.isLoading || allRequirementsQuery.isLoading}
            requirementDisabled={!selectedSprintId && allRequirements.length === 0}
            onRequirementChange={(value: string) => selectRequirement(value === 'all' ? null : value)}
            keyword={keyword}
            onKeywordChange={setKeyword}
            createDisabled={!canCreateSuite}
            onCreate={() => uiTestSuiteSectionRef.current?.openCreateDrawer()}
            refreshing={refreshing}
            onRefresh={() => uiTestSuiteSectionRef.current?.refresh()}
          />

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {!isRequirementLocked ? <>{requirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementsQuery.error)} /> : null}</> : null}
          {!isRequirementLocked ? <>{allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}</> : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !isRequirementLocked && !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : (
            <UiTestSuiteSection
              ref={uiTestSuiteSectionRef}
              requirementId={selectedRequirementId}
              requirementIds={selectedRequirementId ? undefined : visibleRequirementIds}
              selectedSprintId={selectedSprintId}
              sprintOptions={isRequirementLocked ? undefined : drawerSprintOptions}
              requirementOptions={isRequirementLocked ? undefined : displayRequirementFilterOptions}
              sprintName={scope?.sprintName}
              requirementName={scope?.requirementName}
              sprintNameResolver={(suite) => {
                const requirementId = suite.requirementId ?? suite.requirement_id
                const sprintId = requirementId ? requirementSprintMap.get(requirementId) : undefined
                return scope?.sprintName || (sprintId ? sprintNameMap.get(sprintId) ?? sprintId : '-')
              }}
              requirementNameResolver={(suite) => {
                const requirementId = suite.requirementId ?? suite.requirement_id
                return scope?.requirementName || (requirementId ? requirementNameMap.get(requirementId) ?? requirementId : '-')
              }}
              onCreateSprintChange={selectSprint}
              keyword={keyword}
              onClearKeyword={() => setKeyword('')}
              onRefreshingChange={setRefreshing}
            />
          )}
        </section>
      </div>
    </div>
  )
}
