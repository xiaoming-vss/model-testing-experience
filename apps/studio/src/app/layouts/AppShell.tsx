import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { ActionButton } from '@/shared/components/ActionButton'
import { DownOutlined, LogoutOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Dropdown, Layout, Select, Tooltip } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ApiCollectionDetailPage } from '@/features/api-automation/pages/ApiCollectionDetailPage'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { ProfilePage } from '@/features/profile/pages/ProfilePage'
import { ProjectsPage } from '@/features/projects/pages/ProjectsPage'
import { SprintDetailPage } from '@/features/projects/pages/SprintDetailPage'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { UnifiedAiTestingPage } from '@/features/ai-testing/pages/UnifiedAiTestingPage'
import { AiSkillLibraryPage } from '@/features/ai-testing/pages/AiSkillLibraryPage'
import { AiTestingOverviewPage } from '@/features/ai-testing/pages/AiTestingOverviewPage'
import { ApiCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/ApiCaseGenerateTaskDetailPage'
import { FunctionalCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/FunctionalCaseGenerateTaskDetailPage'
import { FunctionalCaseRelationsPage } from '@/features/ai-testing/pages/FunctionalCaseRelationsPage'
import { UiCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/UiCaseGenerateTaskDetailPage'
import { RequirementAnalysisTaskDetailPage } from '@/features/ai-testing/pages/RequirementAnalysisTaskDetailPage'
import { CodeRiskTaskDetailPage } from '@/features/ai-testing/pages/CodeRiskTaskDetailPage'
import { BaseServicesPage } from '@/features/base-services/pages/BaseServicesPage'
import { TestingPage } from '@/features/testing/pages/TestingPage'
import { TestOrderWorkspacePage } from '@/features/test-orders/pages/TestOrderWorkspacePage'
import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import { AppSidebar } from './AppSidebar'
import { useAiTestingTaskCounts } from '@/features/ai-testing/hooks/useAiTestingTaskCounts'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { normalizeProjectId } from '@/utils/format'

const { Header, Content } = Layout

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const { token } = useCurrentUser()
  const { activeProjectId, projects, projectsQuery, setActiveProjectId } = useActiveProject()
  const { activeSprintId, sprintsQuery, selectSprint, sprintSelectorOptions } = useActiveSprint()
  const { kindCounts } = useAiTestingTaskCounts(activeProjectId)
  const showWorkbenchHeader = !location.pathname.startsWith('/profile')

  const shellClassName = `app-shell app-shell-macos${location.pathname.startsWith('/base-services') ? ' app-shell-base-services' : ''}`

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return (
    <Layout className={shellClassName}>
      <AppSidebar designCounts={kindCounts} />
      <Layout>
        <Header className="app-header compact-header">
          <div className="app-header-main">
            {showWorkbenchHeader ? (
              <div className="project-header-bar project-header-bar-select-only">
                <div className="project-selector-wrap">
                  <span className="project-selector-label">当前项目</span>
                  <span className="project-separator">/</span>
                  <Select
                    className="project-select"
                    loading={projectsQuery.isLoading}
                    value={activeProjectId}
                    placeholder="请选择项目"
                    suffixIcon={<DownOutlined />}
                    options={projects.map((project) => ({ label: project.name, value: normalizeProjectId(project) }))}
                    onChange={setActiveProjectId}
                    variant="borderless"
                  />
                  {activeProjectId ? (
                    <>
                      <span className="project-selector-divider" />
                      <span className="project-selector-label">当前迭代</span>
                      <span className="project-separator">/</span>
                      <Select
                        className="project-select sprint-select"
                        loading={sprintsQuery.isLoading}
                        value={activeSprintId ?? 'all'}
                        placeholder="全部迭代"
                        suffixIcon={<DownOutlined />}
                        options={sprintSelectorOptions}
                        onChange={selectSprint}
                        variant="borderless"
                      />
                    </>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          <div className="app-header-feedback" role="note" aria-label="测试阶段反馈联系方式">
            <span className="app-header-feedback-badge">测试阶段</span>
            <span>需求、想法和问题，请联系 <a href="mailto:limingjiang.x@gmail.com">limingjiang.x@gmail.com</a></span>
          </div>
          <div className="app-header-actions">
            {showWorkbenchHeader ? <ActionButton type="primary" className="app-header-create-project action-btn-create" operation="create" onClick={() => { useWorkbenchStore.getState().openProjectModal(); navigate('/projects') }}>新建项目</ActionButton> : null}
            <ThemeSelect />
            <Dropdown
              menu={{
                items: [
                  { key: 'profile', icon: <SettingOutlined />, label: '个人设置' },
                  { type: 'divider' },
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    danger: true,
                  },
                ],
                onClick: ({ key }) => {
                  if (key === 'profile') navigate('/profile')
                  if (key === 'logout') {
                    logout()
                    navigate('/login', { replace: true })
                  }
                },
              }}
              trigger={['click']}
            >
              <Tooltip title="当前用户">
                <Button type="text" shape="circle" icon={<UserOutlined />} />
              </Tooltip>
            </Dropdown>
          </div>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} />
            <Route path="/testing" element={<TestingPage />} />
            <Route path="/test-cases" element={<Navigate to="/testing?tab=library" replace />} />
            <Route path="/test-orders/:orderId" element={<TestOrderWorkspacePage />} />
            <Route path="/ai-testing" element={<AiTestingOverviewPage />} />
            <Route path="/ai-testing/skills" element={<Navigate to="/base-services?tab=skills" replace />} />
            <Route path="/ai-testing/tasks" element={<UnifiedAiTestingPage />} />
            <Route path="/ai-testing/tasks/:taskId" element={<ApiCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/function-tasks/:taskId" element={<FunctionalCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/function-tasks/:taskId/runs/:runId/graph" element={<FunctionalCaseRelationsPage />} />
            <Route path="/ai-testing/ui-tasks/:taskId" element={<UiCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/requirement-analysis-tasks/:taskId" element={<RequirementAnalysisTaskDetailPage />} />
            <Route path="/ai-testing/code-risk-tasks/:taskId" element={<CodeRiskTaskDetailPage />} />
            <Route path="/base-services" element={<BaseServicesPage skillLibrary={<div className="ai-testing-page tp-list-surface ai-skill-library-page tp-surface"><AiSkillLibraryPage embedded /></div>} />} />
            <Route path="/api-automation" element={<Navigate to="/testing?tab=api" replace />} />
            <Route path="/api-automation/collections/:collectionId" element={<ApiCollectionDetailPage />} />
            <Route path="/ui-automation" element={<Navigate to="/testing?tab=ui" replace />} />
            <Route path="/ui-automation/suites/:suiteId" element={<UiTestSuiteCasePage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

