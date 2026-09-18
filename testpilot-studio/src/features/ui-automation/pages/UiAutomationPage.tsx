import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Empty, Select, Typography } from 'antd'
import { Space } from 'antd'

import { useMemo, useRef } from 'react'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { UiTestSuiteSection, type UiTestSuiteSectionRef } from '@/features/ui-automation/components/UiTestSuiteSection'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import type { Requirement } from '@/services/api'
import { getErrorMessage, normalizeRequirementId, normalizeSprintId } from '@/utils/format'

const { Text } = Typography

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
  return (
    <div className="workbench-page api-automation-page functional-test-page ui-test-page">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel">
          <div className="panel-header api-panel-header">
            <div className="requirement-panel-head">
              <Text strong>UI测试集</Text>
              {!isRequirementLocked ? (
                <div className="api-filter-group">
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">迭代</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'}
                      options={sprintFilterOptions}
                      loading={sprintsQuery.isLoading}
                      placeholder="请选择迭代"
                      onChange={(value: string) => {
                        selectSprint(value === 'all' ? null : value)
                        if (value === 'all') {
                          selectRequirement(null)
                        }
                      }}
                    />
                  </div>
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">需求</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'}
                      options={displayRequirementFilterOptions}
                      loading={requirementsQuery.isLoading || allRequirementsQuery.isLoading}
                      placeholder="请选择需求"
                      disabled={!selectedSprintId && allRequirements.length === 0}
                      onChange={(value: string) => selectRequirement(value === 'all' ? null : value)}
                    />
                  </div>
                </div>
              ) : null}
            </div>
            <Space size={8}>
              <ProjectActionButton action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                disabled={!activeProjectId || sprints.length === 0}
                onClick={() => uiTestSuiteSectionRef.current?.openCreateDrawer()}
              >
                新建测试集
              </ProjectActionButton>
            </Space>
          </div>

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
              showInlineCreateButton={false}
            />
          )}
        </section>
      </div>
    </div>
  )
}
