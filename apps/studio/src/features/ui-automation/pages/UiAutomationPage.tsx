import { ListEmptyState } from '@/shared/components/ListEmptyState'
import { Alert } from 'antd'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useProjectRequirementOptions } from '@/domain/projects/hooks/useProjectRequirementOptions'
import { EnvironmentDrawer } from '@/domain/projects/components/EnvironmentDrawer'
import { UiSuiteListToolbar } from '@/features/ui-automation/components/UiSuiteListToolbar'
import { UiTestSuiteSection, type UiTestSuiteSectionRef } from '@/features/ui-automation/components/UiTestSuiteSection'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { api, listItems } from '@/services/api'
import { getErrorMessage, normalizeRequirementId } from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import suiteStyles from '@/features/ui-automation/styles/ui-suite.module.css'

type UiAutomationPageScope = {
  projectId?: string
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
  const { allRequirements, allRequirementsQuery, requirementNameMap } =
    useProjectRequirementOptions({ activeProjectId })
  const [requirementFilterId, setRequirementFilterId] = useState<string | undefined>(scope?.requirementId)
  const selectedRequirementId = scope?.requirementId ?? requirementFilterId
  const requirementFilterOptions = useMemo(
    () => [
      { label: '全部需求', value: 'all' },
      ...allRequirements.map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    ],
    [allRequirements],
  )
  const requirementsLoading = allRequirementsQuery.isLoading
  const canCreateSuite = Boolean(activeProjectId)
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
    <div className={`workbench-page api-automation-page functional-test-page tp-list-surface ui-test-page tp-surface ${suiteStyles.scope}`}>
      <div className="api-automation-content">
        <section className="workbench-panel workbench-panel-flat workbench-board-panel tp-board tp-list-panel">

          <UiSuiteListToolbar
            showScopeFilters={!isRequirementLocked}
            requirementValue={selectedRequirementId ?? 'all'}
            requirementOptions={requirementFilterOptions}
            requirementLoading={requirementsLoading}
            requirementDisabled={!activeProjectId || allRequirements.length === 0}
            onRequirementChange={(value: string) =>
              setRequirementFilterId(value === 'all' ? undefined : value)
            }
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

          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
          {!isRequirementLocked ? <>{allRequirementsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} /> : null}</> : null}

          {!activeProjectId ? (
            <ListEmptyState description="请先选择项目" />
          ) : (
            <UiTestSuiteSection
              ref={uiTestSuiteSectionRef}
              projectId={activeProjectId}
              requirementId={selectedRequirementId}
              requirementOptions={isRequirementLocked ? undefined : requirementFilterOptions}
              requirementName={scope?.requirementName}
              requirementNameResolver={(suite) => {
                const requirementId = suite.requirementId ?? suite.requirement_id
                return scope?.requirementName || (requirementId ? requirementNameMap.get(requirementId) ?? requirementId : '项目级')
              }}
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
