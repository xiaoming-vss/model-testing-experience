import { Alert, Empty } from 'antd'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { EnvironmentDrawer } from '@/features/projects/components/EnvironmentDrawer'
import { UiSuiteListToolbar } from '@/features/ui-automation/components/UiSuiteListToolbar'
import { UiTestSuiteSection, type UiTestSuiteSectionRef } from '@/features/ui-automation/components/UiTestSuiteSection'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { api, listItems, type Requirement } from '@/services/api'
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
    requirementFilterOptions,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
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
  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', activeProjectId, 'ui'],
    queryFn: () => api.getApiEnvironments(activeProjectId!, 'ui'),
    enabled: Boolean(activeProjectId),
  })
  const uiEnvironments = useMemo(() => listItems(environmentsQuery.data), [environmentsQuery.data])
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState('')
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const defaultEnvironmentId = useMemo(
    () => (uiEnvironments.find((item) => item.isDefault) ?? uiEnvironments[0])?.environmentId ?? '',
    [uiEnvironments],
  )
  const resolvedEnvironmentId = selectedEnvironmentId || defaultEnvironmentId
  useEffect(() => {
    // 切换项目后，上一个项目的环境选择不再有效，回到新项目的默认环境。
    setSelectedEnvironmentId('')
  }, [activeProjectId])
  const environmentOptions = useMemo(
    () =>
      uiEnvironments
        .map((item) => ({ label: item.name, value: item.environmentId ?? '' }))
        .filter((item) => item.value),
    [uiEnvironments],
  )
  return (
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface ui-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board tp-list-panel">

          <UiSuiteListToolbar
            showScopeFilters={!isRequirementLocked}
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
            environmentId={resolvedEnvironmentId}
            environmentOptions={environmentOptions}
            environmentsLoading={environmentsQuery.isLoading}
            onEnvironmentChange={setSelectedEnvironmentId}
            onOpenEnvironments={() => setEnvironmentDrawerOpen(true)}
          />

          {sprintsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} /> : null}
          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
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
              environmentId={resolvedEnvironmentId}
              onOpenEnvironments={() => setEnvironmentDrawerOpen(true)}
            />
          )}
        </section>
      </div>

      <EnvironmentDrawer
        open={environmentDrawerOpen}
        projectId={activeProjectId}
        kind="ui"
        currentEnvironmentId={resolvedEnvironmentId}
        onClose={() => setEnvironmentDrawerOpen(false)}
        onSelectEnvironment={(environmentId) => setSelectedEnvironmentId(environmentId ?? '')}
      />
    </div>
  )
}
